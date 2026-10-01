import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/models/models.dart';
import '../../core/services/api_client.dart';
import '../../core/services/recent_searches.dart';

/// State for the user dashboard: village selection, query, results, paging,
/// suggestions and recent searches.
class VoterSearchController extends ChangeNotifier {
  VoterSearchController(this.api, this.recentStore);

  final ApiClient api;
  final RecentSearches recentStore;

  // Data ------------------------------------------------------------------
  List<Village> villages = const [];
  PublicStats? stats;
  List<String> recent = const [];
  List<Suggestion> suggestions = const [];

  // Search state ----------------------------------------------------------
  String selectedVillage = ''; // '' = all villages
  String query = '';
  SearchResponse? response;
  bool loading = false;
  bool bootLoading = true;
  bool villagesLoading = true;
  String? error;
  int page = 1;
  static const pageSize = 10;

  Timer? _suggestDebounce;
  Timer? _villageRetry;
  bool _suggestBusy = false;
  String? _queuedSuggestion;
  int _searchSeq = 0;
  bool _disposed = false;

  /// Optional deep link: `/?q=...&village=...` runs a search on load.
  Future<void> init({
    String initialQuery = '',
    String initialVillage = '',
  }) async {
    bootLoading = true;
    notifyListeners();
    String savedVillage = '';
    try {
      final local = await Future.wait([
        recentStore.load(),
        recentStore.loadVillage(),
        recentStore.loadVillages(),
      ]);
      recent = local[0] as List<String>;
      savedVillage = local[1] as String;
      villages = local[2] as List<Village>;
      _restoreVillage(savedVillage, initialVillage);
      if (!_disposed) notifyListeners();
    } catch (_) {
      // Browser storage is optional; network loading below still proceeds.
    }

    await Future.wait([
      _loadVillages(savedVillage: savedVillage, initialVillage: initialVillage),
      _loadStats(),
    ]);
    bootLoading = false;
    if (!_disposed) notifyListeners();
    if (initialQuery.trim().isNotEmpty) {
      query = initialQuery.trim();
      await search(query);
    }
  }

  Future<void> refreshStats() async {
    await Future.wait([_loadStats(), _loadVillages()]);
    if (!_disposed) notifyListeners();
  }

  Future<void> _loadStats() async {
    try {
      stats = await api.stats();
    } catch (_) {
      // Statistics must never prevent village selection or searching.
    }
  }

  Future<void> _loadVillages({
    String savedVillage = '',
    String initialVillage = '',
    int attempts = 3,
  }) async {
    villagesLoading = villages.isEmpty;
    if (!_disposed) notifyListeners();
    for (var attempt = 0; attempt < attempts; attempt++) {
      try {
        final loaded = await api.villages();
        if (loaded.isEmpty) {
          throw const FormatException('Village list is empty');
        }
        villages = loaded;
        villagesLoading = false;
        _villageRetry?.cancel();
        _restoreVillage(savedVillage, initialVillage);
        unawaited(recentStore.saveVillages(loaded));
        if (!_disposed) notifyListeners();
        return;
      } catch (_) {
        if (attempt + 1 < attempts) {
          await Future<void>.delayed(
            Duration(milliseconds: 400 * (attempt + 1)),
          );
        }
      }
    }
    villagesLoading = false;
    if (villages.isEmpty) _scheduleVillageRetry();
    if (!_disposed) notifyListeners();
  }

  void _restoreVillage(String savedVillage, String initialVillage) {
    if (villages.any((v) => v.name == savedVillage)) {
      selectedVillage = savedVillage;
    }
    if (initialVillage.isNotEmpty &&
        villages.any((v) => v.name == initialVillage)) {
      selectedVillage = initialVillage;
    }
  }

  void _scheduleVillageRetry() {
    _villageRetry?.cancel();
    _villageRetry = Timer(const Duration(seconds: 5), () {
      if (!_disposed && villages.isEmpty) unawaited(_loadVillages(attempts: 2));
    });
  }

  void selectVillage(String village) {
    if (selectedVillage == village) return;
    selectedVillage = village;
    recentStore.saveVillage(village);
    notifyListeners();
    if (query.trim().isNotEmpty) search(query);
  }

  void onQueryChanged(String text) {
    query = text;
    _suggestDebounce?.cancel();
    final minimumLength = selectedVillage.isEmpty ? 3 : 2;
    if (text.trim().length < minimumLength) {
      _queuedSuggestion = null;
      if (suggestions.isNotEmpty) {
        suggestions = const [];
        notifyListeners();
      }
      return;
    }
    _suggestDebounce = Timer(const Duration(milliseconds: 450), () {
      _queueSuggestion(text);
    });
  }

  Future<void> _queueSuggestion(String text) async {
    _queuedSuggestion = text;
    if (_suggestBusy) return;
    _suggestBusy = true;
    try {
      while (_queuedSuggestion != null) {
        final requested = _queuedSuggestion!;
        _queuedSuggestion = null;
        try {
          final result = await api.suggest(requested, village: selectedVillage);
          if (query == requested) {
            suggestions = result;
            notifyListeners();
          }
        } catch (_) {
          // Suggestions are optional; the explicit Search action remains usable.
        }
      }
    } finally {
      _suggestBusy = false;
    }
  }

  void clearSuggestions() {
    _queuedSuggestion = null;
    if (suggestions.isNotEmpty) {
      suggestions = const [];
      notifyListeners();
    }
  }

  Future<void> search(String text, {int toPage = 1}) async {
    final q = text.trim();
    query = q;
    suggestions = const [];
    _queuedSuggestion = null;
    _suggestDebounce?.cancel();
    if (q.isEmpty) {
      response = null;
      error = null;
      notifyListeners();
      return;
    }
    final seq = ++_searchSeq;
    loading = true;
    error = null;
    page = toPage;
    notifyListeners();
    try {
      final res = await api.search(
        q,
        village: selectedVillage,
        page: toPage,
        pageSize: pageSize,
      );
      if (seq != _searchSeq) return; // stale
      response = res;
      if (toPage == 1) recent = await recentStore.add(q);
    } catch (e) {
      if (seq != _searchSeq) return;
      error = _msg(e);
      response = null;
    } finally {
      if (seq == _searchSeq) {
        loading = false;
        notifyListeners();
      }
    }
  }

  Future<void> goToPage(int p) => search(query, toPage: p);

  Future<void> removeRecent(String q) async {
    recent = await recentStore.remove(q);
    notifyListeners();
  }

  Future<void> clearRecent() async {
    await recentStore.clear();
    recent = const [];
    notifyListeners();
  }

  void clear() {
    query = '';
    response = null;
    error = null;
    suggestions = const [];
    notifyListeners();
  }

  String _msg(Object e) {
    if (e is ApiException) return e.message;
    final s = e.toString();
    if (s.contains('SocketException') ||
        s.contains('Failed to fetch') ||
        s.contains('ClientException')) {
      return 'सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट तपासा.';
    }
    if (s.contains('TimeoutException'))
      // ignore: curly_braces_in_flow_control_structures
      return 'विनंतीला खूप वेळ लागला. पुन्हा प्रयत्न करा.';
    return 'अनपेक्षित त्रुटी: $s';
  }

  @override
  void dispose() {
    _disposed = true;
    _suggestDebounce?.cancel();
    _villageRetry?.cancel();
    super.dispose();
  }
}
