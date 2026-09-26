import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_theme.dart';

/// Non-web fallback: hand the PDF to the system viewer.
Widget buildPdfFrame(String url) => _Fallback(url: url);

class _Fallback extends StatelessWidget {
  const _Fallback({required this.url});
  final String url;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.picture_as_pdf_rounded, size: 56, color: AppColors.saffron),
          const SizedBox(height: 12),
          const Text('PDF बाह्य व्ह्यूअरमध्ये उघडले जाईल', style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.open_in_new_rounded),
            label: const Text('PDF उघडा'),
          ),
        ],
      ),
    );
  }
}
