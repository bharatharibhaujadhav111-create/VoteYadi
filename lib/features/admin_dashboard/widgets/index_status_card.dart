import 'package:flutter/material.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/common_widgets.dart';

/// Search-index health: totals, status, version, last indexed, progress bar.
class IndexStatusCard extends StatelessWidget {
  const IndexStatusCard({required this.status, required this.busy, required this.onRebuild, super.key});
  final IndexStatus? status;
  final bool busy;
  final VoidCallback onRebuild;

  @override
  Widget build(BuildContext context) {
    final s = status;
    final indexing = s?.isIndexing ?? false;
    final narrow = MediaQuery.sizeOf(context).width < 640;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Expanded(child: SectionTitle(icon: Icons.manage_search_rounded, title: 'Search Index')),
              _StatusBadge(status: s?.status ?? 'loading'),
            ],
          ),
          const SizedBox(height: 14),
          LayoutBuilder(
            builder: (context, c) {
              final cols = c.maxWidth < 520 ? 2 : 4;
              final w = (c.maxWidth - (cols - 1) * 10) / cols;
              final tiles = [
                _Tile('Total PDFs', s == null ? '—' : '${s.totalPdfs}', Icons.picture_as_pdf_rounded, AppColors.saffron, sub: s == null ? '' : '${s.indexedPdfs} indexed'),
                _Tile('Indexed voters', s == null ? '—' : Formatters.count(s.totalRecords), Icons.people_alt_rounded, AppColors.purple),
                _Tile('Index version', s == null ? '—' : 'v${s.version}', Icons.layers_rounded, AppColors.blue, sub: s?.ocrAvailable == true ? 'OCR ready' : 'OCR unavailable'),
                _Tile('Last indexed', Formatters.relative(s?.lastIndexedAt), Icons.schedule_rounded, AppColors.green, sub: s?.lastDurationSec == null ? '' : 'took ${s!.lastDurationSec!.toStringAsFixed(1)}s'),
              ];
              return Wrap(spacing: 10, runSpacing: 10, children: [for (final t in tiles) SizedBox(width: w, child: t)]);
            },
          ),
          if (indexing && s != null) ...[
            const SizedBox(height: 16),
            Row(
              children: [
                const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.saffron)),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    s.progress.total == 0
                        ? 'Preparing index...'
                        : 'PDF ${(s.progress.filesDone + 1).clamp(1, s.progress.filesTotal < 1 ? 1 : s.progress.filesTotal)} / ${s.progress.filesTotal}  ·  page ${s.progress.current} / ${s.progress.total}${s.progress.file.isEmpty ? '' : '  ·  ${s.progress.file}'}',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
                Text('${s.progress.percent.toStringAsFixed(0)}%', style: const TextStyle(fontWeight: FontWeight.w800, color: AppColors.saffronDark)),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: s.progress.total == 0 ? null : (s.progress.percent / 100).clamp(0.0, 1.0),
                minHeight: 8,
                color: AppColors.saffron,
                backgroundColor: AppColors.saffronLight,
              ),
            ),
          ],
          if (s?.error != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: const Color(0xFFFDECEC), borderRadius: BorderRadius.circular(8)),
              child: Row(children: [
                const Icon(Icons.error_outline_rounded, color: AppColors.danger, size: 18),
                const SizedBox(width: 8),
                Expanded(child: Text(s!.error!, style: const TextStyle(color: AppColors.danger, fontSize: 12.5))),
              ]),
            ),
          ],
          const SizedBox(height: 14),
          Row(
            children: [
              if (!narrow)
                const Expanded(
                  child: Text(
                    'The index is rebuilt automatically whenever a PDF is uploaded, replaced, renamed or deleted. PDFs remain the only source of truth.',
                    style: TextStyle(fontSize: 12, color: AppColors.textMuted),
                  ),
                ),
              if (narrow) const Spacer(),
              ElevatedButton.icon(
                onPressed: busy || indexing ? null : onRebuild,
                icon: const Icon(Icons.refresh_rounded, size: 18),
                label: const Text('Rebuild Search Index'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final (label, color, icon) = switch (status) {
      'ready' => ('Ready', AppColors.green, Icons.check_circle_rounded),
      'indexing' => ('Indexing', AppColors.saffron, Icons.sync_rounded),
      'error' => ('Error', AppColors.danger, Icons.error_rounded),
      'empty' => ('Empty', AppColors.textMuted, Icons.inbox_rounded),
      _ => ('Loading', AppColors.textMuted, Icons.hourglass_empty_rounded),
    };
    return Pill(label: label, icon: icon, color: color.withValues(alpha: 0.12), textColor: color);
  }
}

class _Tile extends StatelessWidget {
  const _Tile(this.label, this.value, this.icon, this.color, {this.sub = ''});
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final String sub;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: AppColors.surface, borderRadius: BorderRadius.circular(10)),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(9)),
            child: Icon(icon, color: color, size: 19),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 11, color: AppColors.textMuted, fontWeight: FontWeight.w600)),
                FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft, child: Text(value, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900, color: AppColors.navyText))),
                if (sub.isNotEmpty) Text(sub, style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
