import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/models.dart';

/// Thin HTTP client around the FastAPI backend.
///
/// In production the Flutter web build is served by the backend itself, so
/// relative URLs work.  For local development set [baseUrl] explicitly, e.g.
/// `ApiClient(baseUrl: 'http://localhost:8000')`.
class ApiClient {
  ApiClient({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ?? _defaultBaseUrl(),
        _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  static String _defaultBaseUrl() {
    const fromEnv = String.fromEnvironment('API_BASE_URL', defaultValue: '');
    if (fromEnv.isNotEmpty) return fromEnv;
    if (kIsWeb) return Uri.base.origin; // same origin as the served app
    return 'http://localhost:8000';
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    final clean = <String, String>{};
    query?.forEach((k, v) {
      if (v.isNotEmpty) clean[k] = v;
    });
    return Uri.parse('$baseUrl$path').replace(queryParameters: clean.isEmpty ? null : clean);
  }

  Future<Map<String, dynamic>> _get(String path, [Map<String, String>? query]) async {
    final res = await _client.get(_uri(path, query)).timeout(const Duration(seconds: 30));
    return _decode(res);
  }

  Future<Map<String, dynamic>> _post(String path, {Object? body, Map<String, String>? query}) async {
    final res = await _client
        .post(_uri(path, query), headers: {'Content-Type': 'application/json'}, body: body == null ? null : jsonEncode(body))
        .timeout(const Duration(seconds: 60));
    return _decode(res);
  }

  Future<Map<String, dynamic>> _delete(String path, [Map<String, String>? query]) async {
    final res = await _client.delete(_uri(path, query)).timeout(const Duration(seconds: 60));
    return _decode(res);
  }

  Map<String, dynamic> _decode(http.Response res) {
    Map<String, dynamic> data = const {};
    try {
      final parsed = jsonDecode(utf8.decode(res.bodyBytes));
      if (parsed is Map<String, dynamic>) data = parsed;
    } catch (_) {
      // non-JSON body
    }
    if (res.statusCode >= 400) {
      final detail = data['detail'];
      String msg;
      if (detail is List) {
        msg = detail.map((e) => e is Map ? '${e['file']}: ${e['error']}' : e.toString()).join('\n');
      } else {
        msg = detail?.toString() ?? 'Request failed (${res.statusCode})';
      }
      throw ApiException(msg, statusCode: res.statusCode);
    }
    return data;
  }

  // ------------------------------------------------------------ public API
  Future<SearchResponse> search(String q, {String village = '', int page = 1, int pageSize = 20, bool ai = true}) async {
    final j = await _get('/api/search', {
      'q': q,
      'village': village,
      'page': '$page',
      'page_size': '$pageSize',
      'ai': ai ? 'true' : 'false',
    });
    return SearchResponse.fromJson(j);
  }

  Future<List<Suggestion>> suggest(String q, {String village = '', int limit = 8}) async {
    final j = await _get('/api/suggest', {'q': q, 'village': village, 'limit': '$limit'});
    final items = (j['items'] as List?) ?? const [];
    if (items.isNotEmpty) {
      return items.map((e) => Suggestion.fromJson(e as Map<String, dynamic>)).toList();
    }
    return ((j['suggestions'] as List?) ?? const [])
        .cast<String>()
        .map((t) => Suggestion(text: t, name: t, relationName: '', relationType: '', village: '', pdf: '', page: 1, age: '', gender: ''))
        .toList();
  }

  Future<List<Village>> villages() async {
    final j = await _get('/api/villages');
    return ((j['villages'] as List?) ?? const []).map((e) => Village.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<PublicStats> stats() async => PublicStats.fromJson(await _get('/api/stats'));

  String viewUrl(String pdfId, {int? page}) {
    final encoded = pdfId.split('/').map(Uri.encodeComponent).join('/');
    final base = '$baseUrl/pdf/view/$encoded';
    return page == null ? base : '$base#page=$page';
  }

  String downloadUrl(String pdfId) {
    final encoded = pdfId.split('/').map(Uri.encodeComponent).join('/');
    return '$baseUrl/pdf/download/$encoded';
  }

  // ------------------------------------------------------------- admin API
  Future<({List<Village> villages, int unassigned})> adminVillages() async {
    final j = await _get('/api/admin/villages');
    return (
      villages: ((j['villages'] as List?) ?? const []).map((e) => Village.fromJson(e as Map<String, dynamic>)).toList(),
      unassigned: (j['unassigned_pdfs'] as num?)?.toInt() ?? 0,
    );
  }

  Future<String> addVillage(String name) async {
    final j = await _post('/api/admin/villages', body: {'name': name});
    return j['name'] as String? ?? name;
  }

  Future<void> renameVillage(String oldName, String newName) =>
      _post('/api/admin/villages/rename', body: {'old_name': oldName, 'new_name': newName});

  Future<void> deleteVillage(String name) => _delete('/api/admin/villages/${Uri.encodeComponent(name)}');

  Future<({List<PdfFile> pdfs, IndexStatus index})> adminPdfs({String q = '', String? village}) async {
    final query = {'q': q};
    if (village != null) query['village'] = village;
    final j = await _get('/api/admin/pdfs', query);
    return (
      pdfs: ((j['pdfs'] as List?) ?? const []).map((e) => PdfFile.fromJson(e as Map<String, dynamic>)).toList(),
      index: IndexStatus.fromJson((j['index'] as Map?)?.cast<String, dynamic>() ?? const {}),
    );
  }

  Future<IndexStatus> indexStatus() async => IndexStatus.fromJson(await _get('/api/admin/index/status'));

  Future<IndexStatus> rebuildIndex({bool full = true}) async =>
      IndexStatus.fromJson(await _post('/api/admin/index/rebuild', query: {'full': full ? 'true' : 'false'}));

  Future<void> deletePdf(String id) => _delete('/api/admin/pdfs', {'id': id});

  Future<void> renamePdf(String id, String newName) => _post('/api/admin/pdfs/rename', body: {'id': id, 'new_name': newName});

  Future<void> movePdf(String id, String village) => _post('/api/admin/pdfs/move', body: {'id': id, 'village': village});

  /// Upload one or more PDFs into [village] ("" = unassigned).
  Future<({List<PdfFile> saved, List<String> errors})> uploadPdfs(
    List<({String name, Uint8List bytes})> files, {
    String village = '',
    bool replace = false,
    void Function(double progress)? onProgress,
  }) async {
    final req = http.MultipartRequest('POST', _uri('/api/admin/pdfs/upload', {'replace': replace ? 'true' : 'false'}));
    req.fields['village'] = village;
    for (final f in files) {
      req.files.add(http.MultipartFile.fromBytes('files', f.bytes, filename: f.name));
    }
    final streamed = await _client.send(req);
    final res = await http.Response.fromStream(streamed);
    final j = _decode(res);
    final saved = ((j['saved'] as List?) ?? const []).map((e) => PdfFile.fromJson(e as Map<String, dynamic>)).toList();
    final errors = ((j['errors'] as List?) ?? const []).map((e) => e is Map ? '${e['file']}: ${e['error']}' : '$e').toList();
    return (saved: saved, errors: errors);
  }

  Future<PdfFile> replacePdf(String id, String fileName, Uint8List bytes) async {
    final req = http.MultipartRequest('POST', _uri('/api/admin/pdfs/replace'));
    req.fields['id'] = id;
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: fileName));
    final res = await http.Response.fromStream(await _client.send(req));
    return PdfFile.fromJson(_decode(res));
  }
}
