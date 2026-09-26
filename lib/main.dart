import 'package:flutter/material.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:provider/provider.dart';

import 'core/services/api_client.dart';
import 'core/theme/app_theme.dart';
import 'features/admin_dashboard/admin_dashboard_page.dart';
import 'features/pdf_viewer/pdf_viewer.dart';
import 'features/user_dashboard/user_dashboard_page.dart';

void main() {
  usePathUrlStrategy(); // clean URLs: "/" and "/super-admin"
  runApp(const VoterFinderApp());
}

class VoterFinderApp extends StatelessWidget {
  const VoterFinderApp({super.key});

  @override
  Widget build(BuildContext context) {
    final api = ApiClient();
    return MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: api),
        Provider<PdfViewer>(create: (_) => PdfViewer(api)),
      ],
      child: MaterialApp(
        title: 'मतदार यादी शोध केंद्र | Voter Finder',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        initialRoute: '/',
        onGenerateRoute: (settings) {
          final uri = Uri.tryParse(settings.name ?? '/') ?? Uri(path: '/');
          final Widget page = switch (uri.path) {
            '/super-admin' || '/super-admin/' || '/admin' || '/admin/' =>
              const AdminDashboardPage(),
            _ => UserDashboardPage(
                initialQuery: uri.queryParameters['q'] ?? '',
                initialVillage: uri.queryParameters['village'] ?? '',
              ),
          };
          return PageRouteBuilder(
            settings: settings,
            pageBuilder: (_, __, ___) => page,
            transitionsBuilder: (_, anim, __, child) => FadeTransition(opacity: anim, child: child),
            transitionDuration: const Duration(milliseconds: 180),
          );
        },
      ),
    );
  }
}
