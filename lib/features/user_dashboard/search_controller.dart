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
  String? error;
  int page = 1;
  static const pageSize = 10;

  Timer? _suggestDebounce;
  int _searchSeq = 0;

  /// Optional deep link: `/?q=...&village=...` runs a search on load.
  Future<void> init({String initialQuery = '', String initialVillage = ''}) async {
    bootLoading = true;
    notifyListeners();
    try {
      final results = await Future.wait([
        api.villages(),
        api.stats(),
        recentStore.load(),
        recentStore.loadVillage(),
      ]);
      villages = results[0] as List<Village>;
      stats = results[1] as PublicStats;
      recent = results[2] as List<String>;
      final savedVillage = results[3] as String;
      if (villages.any((v) => v.name == savedVillage)) selectedVillage = savedVillage;
      if (initialVillage.isNotEmpty && villages.any((v) => v.name == initialVillage)) selectedVillage = initialVillage;
    } catch (e) {
      error = _msg(e);
    } finally {
      bootLoading = false;
      notifyListeners();
    }
    if (initialQuery.trim().isNotEmpty) {
      query = initialQuery.trim();
      await search(query);
    }
  }

  Future<void> refreshStats() async {
    try {
      stats = await api.stats();
      villages = await api.villages();
      notifyListeners();
    } catch (_) {}
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
    if (text.trim().length < 2) {
      if (suggestions.isNotEmpty) {
        suggestions = const [];
        notifyListeners();
      }
      return;
    }
    _suggestDebounce = Timer(const Duration(milliseconds: 180), () async {
      try {
        final s = await api.suggest(text, village: selectedVillage);
        if (query == text) {
          suggestions = s;
          notifyListeners();
        }
      } catch (_) {}
    });
  }

  void clearSuggestions() {
    if (suggestions.isNotEmpty) {
      suggestions = const [];
      notifyListeners();
    }
  }

  Future<void> search(String text, {int toPage = 1}) async {
    final q = text.trim();
    query = q;
    suggestions = const [];
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
      final res = await api.search(q, village: selectedVillage, page: toPage, pageSize: pageSize);
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
    if (s.contains('SocketException') || s.contains('Failed to fetch') || s.contains('ClientException')) {
      return 'सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट तपासा.';
    }
    if (s.contains('TimeoutException')) return 'विनंतीला खूप वेळ लागला. पुन्हा प्रयत्न करा.';
    return 'अनपेक्षित त्रुटी: $s';
  }

  @override
  void dispose() {
    _suggestDebounce?.cancel();
    super.dispose();
  }
}
