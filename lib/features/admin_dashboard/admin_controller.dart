import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/models/models.dart';
import '../../core/services/api_client.dart';

/// State for the admin dashboard: villages, PDFs, index status + polling.
class AdminController extends ChangeNotifier {
  AdminController(this.api);
  final ApiClient api;

  List<Village> villages = const [];
  int unassignedPdfs = 0;
  List<PdfFile> pdfs = const [];
  IndexStatus? index;
  String pdfQuery = '';
  String? villageFilter; // null = all, '' = unassigned
  bool loading = true;
  bool busy = false;
  String? error;
  double? uploadProgress;

  Timer? _poll;
  int _pollCount = 0;

  Future<void> init() async {
    await refresh();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _tick());
  }

  Future<void> _tick() async {
    try {
      final s = await api.indexStatus();
      final wasIndexing = index?.isIndexing ?? false;
      index = s;
      notifyListeners();
      // GitHub OCR updates PDF rows independently of the local index status.
      // Refresh those rows periodically even when the index never changes.
      if ((wasIndexing && !s.isIndexing) || ++_pollCount % 5 == 0) {
        await refresh(silent: true);
      }
    } catch (_) {}
  }

  Future<void> refresh({bool silent = false}) async {
    if (!silent) {
      loading = true;
      error = null;
      notifyListeners();
    }
    try {
      final v = await api.adminVillages();
      final p = await api.adminPdfs(q: pdfQuery, village: villageFilter);
      villages = v.villages;
      unassignedPdfs = v.unassigned;
      pdfs = p.pdfs;
      index = p.index;
    } catch (e) {
      error = _msg(e);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  void setPdfQuery(String q) {
    pdfQuery = q;
    refresh(silent: true);
  }

  void setVillageFilter(String? v) {
    villageFilter = v;
    refresh(silent: true);
  }

  Future<String?> _run(Future<void> Function() op) async {
    busy = true;
    notifyListeners();
    try {
      await op();
      await refresh(silent: true);
      return null;
    } catch (e) {
      return _msg(e);
    } finally {
      busy = false;
      uploadProgress = null;
      notifyListeners();
    }
  }

  Future<String?> addVillage(String name) => _run(() => api.addVillage(name));
  Future<String?> renameVillage(String o, String n) =>
      _run(() => api.renameVillage(o, n));
  Future<String?> deleteVillage(String name) =>
      _run(() => api.deleteVillage(name));
  Future<String?> deletePdf(String id) => _run(() => api.deletePdf(id));
  Future<String?> renamePdf(String id, String newName) =>
      _run(() => api.renamePdf(id, newName));
  Future<String?> movePdf(String id, String village) =>
      _run(() => api.movePdf(id, village));
  Future<String?> retryPdf(String id) => _run(() => api.retryPdf(id));
  Future<String?> rebuild({bool full = true}) => _run(() async {
    index = await api.rebuildIndex(full: full);
  });

  Future<({int saved, List<String> errors})> upload(
    List<({String name, Uint8List bytes})> files,
    String village,
  ) async {
    busy = true;
    uploadProgress = 0;
    notifyListeners();
    try {
      final r = await api.uploadPdfs(files, village: village);
      await refresh(silent: true);
      return (saved: r.saved.length, errors: r.errors);
    } catch (e) {
      return (saved: 0, errors: [_msg(e)]);
    } finally {
      busy = false;
      uploadProgress = null;
      notifyListeners();
    }
  }

  Future<String?> replacePdf(String id, String fileName, Uint8List bytes) =>
      _run(() => api.replacePdf(id, fileName, bytes));

  String _msg(Object e) {
    if (e is ApiException) return e.message;
    final s = e.toString();
    if (s.contains('Failed to fetch') ||
        s.contains('SocketException') ||
        s.contains('ClientException')) {
      return 'Cannot reach the server. Is the backend running?';
    }
    return s;
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }
}
