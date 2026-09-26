import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/services/pwa_install.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common_widgets.dart';

class InstallAppBanner extends StatefulWidget {
  const InstallAppBanner({super.key});

  @override
  State<InstallAppBanner> createState() => _InstallAppBannerState();
}

class _InstallAppBannerState extends State<InstallAppBanner> {
  bool _hidden = false;
  bool _installing = false;

  Future<void> _install() async {
    setState(() => _installing = true);
    final accepted = await promptPwaInstall();
    if (!mounted) return;
    setState(() {
      _installing = false;
      if (accepted) _hidden = true;
    });
    if (!accepted) {
      showSnack(
        context,
        'Chrome menu (⋮) उघडा आणि “Install app” किंवा “Add to Home screen” निवडा.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb || isPwaStandalone || _hidden) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        decoration: BoxDecoration(
          color: AppColors.greenLight,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.green.withValues(alpha: 0.28)),
        ),
        child: Row(
          children: [
          const Icon(Icons.install_mobile_rounded, color: AppColors.green),
          const SizedBox(width: 10),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('फोनवर App म्हणून Install करा', style: TextStyle(fontWeight: FontWeight.w800, color: AppColors.navyText)),
                SizedBox(height: 2),
                Text('Chrome मधून थेट Home Screen वर जोडा.', style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            onPressed: _installing ? null : _install,
            style: FilledButton.styleFrom(backgroundColor: AppColors.green, padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10)),
            icon: _installing
                ? const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.download_rounded, size: 18),
            label: const Text('Install'),
          ),
          IconButton(
            tooltip: 'Dismiss',
            onPressed: () => setState(() => _hidden = true),
            icon: const Icon(Icons.close_rounded, size: 19),
          ),
          ],
        ),
      ),
    );
  }
}
