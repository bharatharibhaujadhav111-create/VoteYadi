import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:voter_finder/core/services/api_client.dart';
import 'package:voter_finder/core/theme/app_theme.dart';
import 'package:voter_finder/features/pdf_viewer/pdf_viewer.dart';
import 'package:voter_finder/features/user_dashboard/user_dashboard_page.dart';
import 'package:voter_finder/features/user_dashboard/widgets/results_section.dart';

Map<String, dynamic> _voter(int i) => {
      'id': i,
      'name': 'SONALI JADHAV $i',
      'relation_name': 'AMOL JADHAV',
      'relation_type': 'husband',
      'epic': 'ZCG000000$i',
      'serial': '$i',
      'part': '7',
      'house': '',
      'age': '31',
      'gender': 'Female',
      'page': 8,
      'pdf': 'Tirhe/2026-EROLLGEN-S13-251-SIR-DraftRoll-Revision1-ENG-7-WI.pdf',
      'pdf_name': '2026-EROLLGEN-S13-251-SIR-DraftRoll-Revision1-ENG-7-WI.pdf',
      'village': 'Tirhe',
      'score': 120.0,
    };

http.Response _json(Object body) => http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});

MockClient _mockApi() => MockClient((req) async {
      switch (req.url.path) {
        case '/api/villages':
          return _json({'villages': [{'name': 'Tirhe', 'records': 1710}, {'name': 'Hotgi', 'records': 0}]});
        case '/api/stats':
          return _json({'total_pdfs': 2, 'total_records': 1710, 'total_villages': 2, 'index_status': 'ready', 'index_version': 3});
        case '/api/suggest':
          return _json({
            'suggestions': ['Sonali Jadhav', 'Sonali Babaurav Jadhav'],
            'items': [
              {'text': 'Sonali Jadhav', 'name': 'SONALI JADHAV', 'relation_name': 'AMOL JADHAV', 'relation_type': 'husband', 'village': 'Tirhe', 'pdf': 'Tirhe/x.pdf', 'page': 8, 'age': '31', 'gender': 'Female'},
              {'text': 'Sonali Babaurav Jadhav', 'name': 'SONALI BABAURAV JADHAV', 'relation_name': 'BABAURAV JADHAV', 'relation_type': 'husband', 'village': 'Tirhe', 'pdf': 'Tirhe/x.pdf', 'page': 25, 'age': '30', 'gender': 'Female'},
            ],
          });
        case '/api/search':
          if (req.url.queryParameters['q'] == 'nobody here') {
            return _json({'results': [], 'total': 0, 'page': 1, 'page_size': 10, 'took_ms': 0.5, 'query': {'any_text': 'nobody here'}, 'relaxed': false, 'suggestions': ['Sonali Jadhav']});
          }
          return _json({
            'results': List.generate(5, _voter),
            'total': 5,
            'page': 1,
            'page_size': 10,
            'took_ms': 1.2,
            'query': {'any_text': 'sonali jadav', 'village': 'Tirhe'},
            'relaxed': false,
            'suggestions': [],
          });
      }
      return http.Response('not found', 404);
    });

Widget _app() {
  final api = ApiClient(baseUrl: 'http://test', client: _mockApi());
  return MultiProvider(
    providers: [
      Provider<ApiClient>.value(value: api),
      Provider<PdfViewer>(create: (_) => PdfViewer(api)),
    ],
    child: MaterialApp(theme: AppTheme.light(), home: const UserDashboardPage()),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  for (final size in [const Size(390, 844), const Size(1280, 900)]) {
    testWidgets('type + submit search renders results without errors (${size.width.toInt()}px)', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_app());
      await tester.pumpAndSettle();

      final field = find.byType(TextField);
      expect(field, findsOneWidget);

      await tester.tap(field);
      await tester.pump();
      await tester.enterText(field, 'sonali jadav');
      // Suggestions wait until the user pauses, avoiding a request per key.
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      expect(find.textContaining('यादीतील जुळणारी नावे'), findsOneWidget, reason: 'suggestion dropdown should appear while typing');
      expect(find.textContaining('Amol Jadhav'), findsWidgets, reason: 'suggestions show relation name');

      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byType(ResultCard), findsNWidgets(5));
      expect(find.textContaining('निकाल सापडले'), findsOneWidget);
      // search card is still there
      expect(find.byType(TextField), findsOneWidget);
    });
  }

  testWidgets('no results shows guidance with next steps and actions', (tester) async {
    tester.view.physicalSize = const Size(390, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_app());
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'nobody here');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('या यादीमध्ये नाव सापडले नाही'), findsOneWidget);
    expect(find.text('पुढील प्रक्रिया'), findsOneWidget);
    expect(find.text('Form 6 भरा'), findsOneWidget);
    expect(find.text('अधिकृत यादीत नाव तपासा'), findsOneWidget);
    expect(find.text('Sonali Jadhav'), findsOneWidget, reason: 'did-you-mean chip');
  });
}
