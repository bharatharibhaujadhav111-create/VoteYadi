import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/models.dart';

/// Persists the user's recent searches locally (browser storage on web).
class RecentSearches {
  static const _key = 'recent_searches_v1';
  static const _villageKey = 'selected_village_v1';
  static const _villagesCacheKey = 'villages_cache_v1';
  static const _max = 8;

  Future<List<String>> load() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getStringList(_key) ?? const [];
  }

  Future<List<String>> add(String query) async {
    final q = query.trim();
    if (q.isEmpty) return load();
    final prefs = await SharedPreferences.getInstance();
    final list = List<String>.from(prefs.getStringList(_key) ?? const []);
    list.removeWhere((e) => e.toLowerCase() == q.toLowerCase());
    list.insert(0, q);
    if (list.length > _max) list.removeRange(_max, list.length);
    await prefs.setStringList(_key, list);
    return list;
  }

  Future<List<String>> remove(String query) async {
    final prefs = await SharedPreferences.getInstance();
    final list = List<String>.from(prefs.getStringList(_key) ?? const []);
    list.remove(query);
    await prefs.setStringList(_key, list);
    return list;
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }

  Future<String> loadVillage() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_villageKey) ?? '';
  }

  Future<void> saveVillage(String village) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_villageKey, village);
  }

  Future<List<Village>> loadVillages() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_villagesCacheKey);
    if (raw == null || raw.isEmpty) return const [];
    try {
      final items = jsonDecode(raw) as List<dynamic>;
      return items
          .map((item) => Village.fromJson(item as Map<String, dynamic>))
          .where((village) => village.name.isNotEmpty)
          .toList(growable: false);
    } catch (_) {
      return const [];
    }
  }

  Future<void> saveVillages(List<Village> villages) async {
    if (villages.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _villagesCacheKey,
      jsonEncode([
        for (final village in villages)
          {
            'name': village.name,
            'pdfs': village.pdfs,
            'records': village.records,
          },
      ]),
    );
  }
}
