import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/services/api_client.dart';
import '../../core/services/recent_searches.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common_widgets.dart';
import 'search_controller.dart';
import 'widgets/hero_header.dart';
import 'widgets/info_sections.dart';
import 'widgets/install_app_banner.dart';
import 'widgets/results_section.dart';
import 'widgets/search_card.dart';

/// Public user dashboard ("/").
class UserDashboardPage extends StatelessWidget {
  const UserDashboardPage({
    super.key,
    this.initialQuery = '',
    this.initialVillage = '',
  });

  /// Populated from the URL (`/?q=...&village=...`) for shareable links.
  final String initialQuery;
  final String initialVillage;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (ctx) =>
          VoterSearchController(ctx.read<ApiClient>(), RecentSearches())
            ..init(initialQuery: initialQuery, initialVillage: initialVillage),
      child: const _UserDashboardView(),
    );
  }
}

class _UserDashboardView extends StatelessWidget {
  const _UserDashboardView();

  @override
  Widget build(BuildContext context) {
    final c = context.watch<VoterSearchController>();
    final hasResults = c.response != null || c.loading || c.error != null;
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: RefreshIndicator(
          color: AppColors.saffron,
          onRefresh: c.refreshStats,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: Column(
              children: [
                const HeroHeader(),
                PageContainer(
                  padding: const EdgeInsets.fromLTRB(12, 14, 12, 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SearchCard(),
                      const InstallAppBanner(),
                      const SizedBox(height: 12),
                      if (hasResults) ...[
                        const ResultsSection(),
                        const SizedBox(height: 12),
                      ],
                      if (c.bootLoading)
                        const LoadingIndicator()
                      else ...[
                        StatsRow(stats: c.stats),
                        const SizedBox(height: 12),
                        VillagesCard(
                          villages: c.villages,
                          selected: c.selectedVillage,
                          onSelect: c.selectVillage,
                        ),
                        const SizedBox(height: 12),
                        const HowToCard(),
                      ],
                    ],
                  ),
                ),
                const FooterBand(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
