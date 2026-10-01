import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:voter_finder/core/services/api_client.dart';
import 'package:voter_finder/core/services/recent_searches.dart';
import 'package:voter_finder/features/user_dashboard/search_controller.dart';

void main() {
  test('villages retry independently when statistics and early requests fail', () async {
    SharedPreferences.setMockInitialValues({});
    var villageRequests = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/api/villages') {
        villageRequests++;
        if (villageRequests < 3) return http.Response('temporary failure', 503);
        return http.Response(
          jsonEncode({
            'villages': [
              {'name': 'तिर्‍हे', 'pdfs': 3, 'records': 1200},
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }
      if (request.url.path == '/api/stats') {
        return http.Response('temporary failure', 503);
      }
      return http.Response('not found', 404);
    });
    final controller = VoterSearchController(
      ApiClient(baseUrl: 'https://test.invalid', client: client),
      RecentSearches(),
    );
    addTearDown(controller.dispose);

    await controller.init();

    expect(villageRequests, 3);
    expect(controller.villages.map((village) => village.name), ['तिर्‍हे']);
    expect(controller.villagesLoading, isFalse);
    expect(controller.error, isNull);
  });

  test('cached villages remain visible while a refresh is unavailable', () async {
    SharedPreferences.setMockInitialValues({
      'villages_cache_v1': jsonEncode([
        {'name': 'मार्डी', 'pdfs': 2, 'records': 800},
      ]),
    });
    final client = MockClient((_) async => http.Response('offline', 503));
    final controller = VoterSearchController(
      ApiClient(baseUrl: 'https://test.invalid', client: client),
      RecentSearches(),
    );
    addTearDown(controller.dispose);

    await controller.init();

    expect(controller.villages.map((village) => village.name), ['मार्डी']);
    expect(controller.villagesLoading, isFalse);
  });
}
