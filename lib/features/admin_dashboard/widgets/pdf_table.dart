import 'package:flutter/material.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/common_widgets.dart';

enum PdfAction { view, download, retry, replace, rename, move, delete }

/// Responsive PDF list: table on wide screens, cards on narrow screens.
class PdfTable extends StatelessWidget {
  const PdfTable({required this.pdfs, required this.onAction, super.key});
  final List<PdfFile> pdfs;
  final void Function(PdfFile pdf, PdfAction action) onAction;

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 860;
    if (pdfs.isEmpty) {
      return const EmptyState(
        icon: Icons.folder_open_rounded,
        title: 'No PDFs found',
        subtitle: 'Upload electoral roll PDFs to make them searchable.',
      );
    }
    if (!wide) {
      return Column(
        children: [
          for (var i = 0; i < pdfs.length; i++) ...[
            _PdfCard(pdf: pdfs[i], onAction: onAction),
            if (i < pdfs.length - 1) const SizedBox(height: 8),
          ],
        ],
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: Table(
        columnWidths: const {
          0: FlexColumnWidth(3.2),
          1: FlexColumnWidth(1.4),
          2: FlexColumnWidth(0.9),
          3: FlexColumnWidth(0.8),
          4: FlexColumnWidth(1.1),
          5: FlexColumnWidth(1.6),
          6: FlexColumnWidth(1.5),
          7: FixedColumnWidth(110),
        },
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        children: [
          TableRow(
            decoration: const BoxDecoration(color: AppColors.surface),
            children: const [
              _Th('PDF name'),
              _Th('Village'),
              _Th('Size'),
              _Th('Pages'),
              _Th('Voters'),
              _Th('Uploaded'),
              _Th('Index'),
              _Th('Actions', right: true),
            ],
          ),
          for (final p in pdfs)
            TableRow(
              decoration: const BoxDecoration(
                border: Border(bottom: BorderSide(color: AppColors.border)),
              ),
              children: [
                _Td(
                  Row(
                    children: [
                      const Icon(
                        Icons.picture_as_pdf_rounded,
                        color: AppColors.saffron,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          p.name,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                ),
                _Td(
                  p.village.isEmpty
                      ? const Pill(
                          label: 'Unassigned',
                          color: Color(0xFFFDECEC),
                          textColor: AppColors.danger,
                        )
                      : Pill(
                          label: p.village,
                          icon: Icons.location_on_rounded,
                          color: AppColors.greenLight,
                          textColor: AppColors.green,
                        ),
                ),
                _Td(Text(Formatters.bytes(p.size))),
                _Td(Text('${p.pages}')),
                _Td(Text(Formatters.count(p.records))),
                _Td(
                  Text(
                    Formatters.dateTime(p.uploadedAt),
                    style: const TextStyle(fontSize: 12.5),
                  ),
                ),
                _Td(_IndexPill(p)),
                _Td(
                  Align(
                    alignment: Alignment.centerRight,
                    child: _ActionsMenu(pdf: p, onAction: onAction),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _Th extends StatelessWidget {
  const _Th(this.text, {this.right = false});
  final String text;
  final bool right;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
    child: Text(
      text,
      textAlign: right ? TextAlign.right : TextAlign.left,
      style: const TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w800,
        color: AppColors.textSecondary,
      ),
    ),
  );
}

class _Td extends StatelessWidget {
  const _Td(this.child);
  final Widget child;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
    child: DefaultTextStyle.merge(
      style: const TextStyle(fontSize: 13.5),
      child: child,
    ),
  );
}

class _IndexPill extends StatelessWidget {
  const _IndexPill(this.p);
  final PdfFile p;
  @override
  Widget build(BuildContext context) {
    if (p.indexed) {
      return Tooltip(
        message: p.ocrPages > 0
            ? '${p.ocrPages} page(s) required OCR'
            : 'Text extracted directly',
        child: Pill(
          label: p.ocrPages > 0 ? 'Indexed (OCR)' : 'Indexed',
          icon: Icons.check_circle_rounded,
          color: AppColors.greenLight,
          textColor: AppColors.green,
        ),
      );
    }
    if (p.status == 'needs_review') {
      return Tooltip(
        message: p.error.isEmpty
            ? 'OCR quality checks require review'
            : p.error,
        child: const Pill(
          label: 'Needs review',
          icon: Icons.report_problem_rounded,
          color: Color(0xFFFFE8E5),
          textColor: AppColors.danger,
        ),
      );
    }
    if (p.status == 'processing') {
      return const Pill(
        label: 'Processing',
        icon: Icons.sync_rounded,
        color: AppColors.saffronLight,
        textColor: AppColors.saffronDark,
      );
    }
    if (p.status == 'failed') {
      return Tooltip(
        message: p.error.isEmpty ? 'Indexing failed' : p.error,
        child: const Pill(
          label: 'Failed',
          icon: Icons.error_rounded,
          color: Color(0xFFFFE8E5),
          textColor: AppColors.danger,
        ),
      );
    }
    return const Pill(
      label: 'Pending',
      icon: Icons.hourglass_top_rounded,
      color: AppColors.saffronLight,
      textColor: AppColors.saffronDark,
    );
  }
}

class _ActionsMenu extends StatelessWidget {
  const _ActionsMenu({required this.pdf, required this.onAction});
  final PdfFile pdf;
  final void Function(PdfFile, PdfAction) onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          tooltip: 'View',
          icon: const Icon(Icons.visibility_outlined, size: 20),
          onPressed: () => onAction(pdf, PdfAction.view),
        ),
        PopupMenuButton<PdfAction>(
          tooltip: 'More',
          onSelected: (a) => onAction(pdf, a),
          itemBuilder: (_) => [
            const PopupMenuItem(
              value: PdfAction.download,
              child: ListTile(
                dense: true,
                leading: Icon(Icons.download_rounded),
                title: Text('Download'),
              ),
            ),
            if (pdf.status == 'failed' || pdf.status == 'needs_review')
              const PopupMenuItem(
                value: PdfAction.retry,
                child: ListTile(
                  dense: true,
                  leading: Icon(Icons.restart_alt_rounded),
                  title: Text('Retry indexing'),
                ),
              ),
            const PopupMenuItem(
              value: PdfAction.replace,
              child: ListTile(
                dense: true,
                leading: Icon(Icons.swap_horiz_rounded),
                title: Text('Replace PDF'),
              ),
            ),
            const PopupMenuItem(
              value: PdfAction.rename,
              child: ListTile(
                dense: true,
                leading: Icon(Icons.drive_file_rename_outline_rounded),
                title: Text('Rename'),
              ),
            ),
            const PopupMenuItem(
              value: PdfAction.move,
              child: ListTile(
                dense: true,
                leading: Icon(Icons.drive_file_move_outlined),
                title: Text('Move to village'),
              ),
            ),
            const PopupMenuDivider(),
            const PopupMenuItem(
              value: PdfAction.delete,
              child: ListTile(
                dense: true,
                leading: Icon(
                  Icons.delete_outline_rounded,
                  color: AppColors.danger,
                ),
                title: Text(
                  'Delete',
                  style: TextStyle(color: AppColors.danger),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _PdfCard extends StatelessWidget {
  const _PdfCard({required this.pdf, required this.onAction});
  final PdfFile pdf;
  final void Function(PdfFile, PdfAction) onAction;

  @override
  Widget build(BuildContext context) {
    final p = pdf;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.picture_as_pdf_rounded,
                color: AppColors.saffron,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  p.name,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14.5,
                  ),
                ),
              ),
              _ActionsMenu(pdf: p, onAction: onAction),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              p.village.isEmpty
                  ? const Pill(
                      label: 'Unassigned',
                      color: Color(0xFFFDECEC),
                      textColor: AppColors.danger,
                    )
                  : Pill(
                      label: p.village,
                      icon: Icons.location_on_rounded,
                      color: AppColors.greenLight,
                      textColor: AppColors.green,
                    ),
              Pill(
                label: Formatters.bytes(p.size),
                icon: Icons.sd_storage_outlined,
              ),
              Pill(label: '${p.pages} pages', icon: Icons.menu_book_rounded),
              Pill(
                label: '${Formatters.count(p.records)} voters',
                icon: Icons.people_alt_outlined,
              ),
              _IndexPill(p),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Uploaded ${Formatters.dateTime(p.uploadedAt)}',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}
