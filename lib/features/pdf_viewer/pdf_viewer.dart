import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/services/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common_widgets.dart';
import 'pdf_frame_stub.dart' if (dart.library.js_interop) 'pdf_frame_web.dart';

/// PDF viewer module.
///
/// * [open]     – opens the PDF in a new browser tab at the matching page.
/// * [preview]  – in-app modal preview (iframe on web).
/// * [download] – forces a download of the original PDF.
class PdfViewer {
  PdfViewer(this.api);
  final ApiClient api;

  Future<void> open(BuildContext context, String pdfId, {int? page, int? voterId}) async {
    final url = api.viewUrl(pdfId, page: page, voterId: voterId);
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication, webOnlyWindowName: '_blank');
    if (!ok && context.mounted) showSnack(context, 'PDF उघडता आले नाही', error: true);
  }

  Future<void> download(BuildContext context, String pdfId) async {
    final url = api.downloadUrl(pdfId);
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication, webOnlyWindowName: '_blank');
    if (!ok && context.mounted) showSnack(context, 'PDF डाउनलोड करता आले नाही', error: true);
  }

  Future<void> printSlip(BuildContext context, int voterId) async {
    final ok = await launchUrl(Uri.parse(api.printSlipUrl(voterId)), mode: LaunchMode.externalApplication, webOnlyWindowName: '_blank');
    if (!ok && context.mounted) showSnack(context, 'मतदार स्लिप तयार करता आली नाही', error: true);
  }

  Future<void> preview(BuildContext context, String pdfId, {int? page, int? voterId, String? title}) {
    return showDialog(
      context: context,
      builder: (ctx) => _PdfPreviewDialog(
        url: api.viewUrl(pdfId, page: page, voterId: voterId),
        title: title ?? pdfId,
        page: page,
        onOpen: () => open(ctx, pdfId, page: page, voterId: voterId),
        onDownload: () => download(ctx, pdfId),
      ),
    );
  }
}

class _PdfPreviewDialog extends StatelessWidget {
  const _PdfPreviewDialog({required this.url, required this.title, required this.onOpen, required this.onDownload, this.page});
  final String url;
  final String title;
  final int? page;
  final VoidCallback onOpen;
  final VoidCallback onDownload;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    return Dialog(
      insetPadding: const EdgeInsets.all(12),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        width: size.width.clamp(300, 1100),
        height: size.height * 0.92,
        child: Column(
          children: [
            Container(
              color: AppColors.navy,
              padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
              child: Row(
                children: [
                  const Icon(Icons.picture_as_pdf_rounded, color: AppColors.saffron),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      page == null ? title : '$title  ·  पान $page',
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700, color: Colors.white),
                    ),
                  ),
                  IconButton(tooltip: 'नवीन टॅबमध्ये उघडा', onPressed: onOpen, icon: const Icon(Icons.open_in_new_rounded, color: Colors.white)),
                  IconButton(tooltip: 'डाउनलोड', onPressed: onDownload, icon: const Icon(Icons.download_rounded, color: Colors.white)),
                  IconButton(onPressed: () => Navigator.of(context).pop(), icon: const Icon(Icons.close_rounded, color: Colors.white)),
                ],
              ),
            ),
            Expanded(child: buildPdfFrame(url)),
          ],
        ),
      ),
    );
  }
}
