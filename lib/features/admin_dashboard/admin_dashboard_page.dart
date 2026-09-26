import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/models/models.dart';
import '../../core/services/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common_widgets.dart';
import '../pdf_viewer/pdf_viewer.dart';
import 'admin_controller.dart';
import 'widgets/admin_dialogs.dart';
import 'widgets/index_status_card.dart';
import 'widgets/pdf_table.dart';

/// Admin dashboard ("/admin") – villages, PDFs and the search index.
class AdminDashboardPage extends StatelessWidget {
  const AdminDashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (ctx) => AdminController(ctx.read<ApiClient>())..init(),
      child: const _AdminView(),
    );
  }
}

class _AdminView extends StatefulWidget {
  const _AdminView();

  @override
  State<_AdminView> createState() => _AdminViewState();
}

class _AdminViewState extends State<_AdminView> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _upload(AdminController c, {String? village}) async {
    final sel = await showUploadDialog(context, c.villages, initialVillage: village ?? c.villageFilter);
    if (sel == null || !mounted) return;
    showSnack(context, 'Uploading ${sel.files.length} file(s) to ${sel.village}...');
    final r = await c.upload(sel.files, sel.village);
    if (!mounted) return;
    if (r.errors.isNotEmpty) {
      showSnack(context, '${r.saved} uploaded, ${r.errors.length} failed:\n${r.errors.join('\n')}', error: true);
    } else {
      showSnack(context, '${r.saved} PDF(s) uploaded to ${sel.village}. Indexing started.');
    }
  }

  Future<void> _onPdfAction(AdminController c, PdfFile p, PdfAction a) async {
    final viewer = context.read<PdfViewer>();
    String? err;
    switch (a) {
      case PdfAction.view:
        await viewer.preview(context, p.id, title: p.id);
        return;
      case PdfAction.download:
        await viewer.download(context, p.id);
        return;
      case PdfAction.replace:
        final files = await pickPdfs(multiple: false);
        if (files.isEmpty) return;
        err = await c.replacePdf(p.id, files.first.name, files.first.bytes);
        if (err == null && mounted) showSnack(context, '${p.name} replaced. Re-indexing.');
      case PdfAction.rename:
        final name = await showTextDialog(context, title: 'Rename PDF', label: 'New file name', initial: p.name);
        if (name == null || name.isEmpty || name == p.name) return;
        err = await c.renamePdf(p.id, name);
        if (err == null && mounted) showSnack(context, 'Renamed to $name');
      case PdfAction.move:
        final v = await showVillagePicker(context, c.villages, current: p.village);
        if (v == null || v == p.village) return;
        err = await c.movePdf(p.id, v);
        if (err == null && mounted) showSnack(context, '${p.name} moved to $v');
      case PdfAction.delete:
        final ok = await showConfirmDialog(context, title: 'Delete PDF?', message: '"${p.id}" will be permanently removed from storage and from the search index.');
        if (!ok) return;
        err = await c.deletePdf(p.id);
        if (err == null && mounted) showSnack(context, '${p.name} deleted');
    }
    if (err != null && mounted) showSnack(context, err, error: true);
  }

  Future<void> _villageMenu(AdminController c, Village v, String action) async {
    String? err;
    switch (action) {
      case 'upload':
        await _upload(c, village: v.name);
        return;
      case 'rename':
        final n = await showTextDialog(context, title: 'Rename village', label: 'Village name', initial: v.name);
        if (n == null || n.isEmpty || n == v.name) return;
        err = await c.renameVillage(v.name, n);
      case 'delete':
        final ok = await showConfirmDialog(
          context,
          title: 'Delete village?',
          message: v.pdfs == 0 ? 'Remove "${v.name}" from the list?' : '"${v.name}" and its ${v.pdfs} PDF(s) will be permanently deleted and removed from the index.',
        );
        if (!ok) return;
        err = await c.deleteVillage(v.name);
    }
    if (err != null && mounted) showSnack(context, err, error: true);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.watch<AdminController>();
    final wide = MediaQuery.sizeOf(context).width >= 980;
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: AppColors.navy,
        foregroundColor: Colors.white,
        title: const Row(children: [
          Icon(Icons.admin_panel_settings_rounded),
          SizedBox(width: 8),
          Text('Voter Finder · Admin', style: TextStyle(fontWeight: FontWeight.w800)),
        ]),
        actions: [
          TextButton.icon(
            onPressed: () => Navigator.of(context).pushReplacementNamed('/'),
            icon: const Icon(Icons.public_rounded, color: Colors.white70, size: 18),
            label: const Text('User site', style: TextStyle(color: Colors.white70)),
          ),
          IconButton(tooltip: 'Refresh', onPressed: c.loading ? null : c.refresh, icon: const Icon(Icons.refresh_rounded)),
          const SizedBox(width: 6),
        ],
        bottom: c.busy ? const PreferredSize(preferredSize: Size.fromHeight(3), child: LinearProgressIndicator(minHeight: 3, color: AppColors.saffron, backgroundColor: AppColors.navy)) : null,
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: c.busy ? null : () => _upload(c),
        backgroundColor: AppColors.saffron,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.upload_file_rounded),
        label: const Text('Upload PDFs'),
      ),
      body: SafeArea(
        child: c.loading && c.index == null
            ? const LoadingIndicator(message: 'Loading admin data...')
            : c.error != null && c.index == null
                ? ErrorState(message: c.error!, onRetry: c.refresh)
                : SingleChildScrollView(
                    child: PageContainer(
                      maxWidth: 1240,
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 90),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          IndexStatusCard(
                            status: c.index,
                            busy: c.busy,
                            onRebuild: () async {
                              final err = await c.rebuild();
                              if (!context.mounted) return;
                              showSnack(context, err ?? 'Full index rebuild started', error: err != null);
                            },
                          ),
                          const SizedBox(height: 14),
                          if (wide)
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                SizedBox(width: 300, child: _villagesCard(c)),
                                const SizedBox(width: 14),
                                Expanded(child: _pdfCard(c)),
                              ],
                            )
                          else ...[
                            _villagesCard(c),
                            const SizedBox(height: 14),
                            _pdfCard(c),
                          ],
                        ],
                      ),
                    ),
                  ),
      ),
    );
  }

  Widget _villagesCard(AdminController c) {
    return AppCard(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionTitle(
            icon: Icons.location_on_rounded,
            iconColor: AppColors.green,
            title: 'Villages (${c.villages.length})',
            trailing: IconButton(
              tooltip: 'Add village',
              onPressed: c.busy
                  ? null
                  : () async {
                      final n = await showTextDialog(context, title: 'Add village', label: 'Village name', confirm: 'Add', icon: Icons.add_location_alt_rounded);
                      if (n == null || n.isEmpty) return;
                      final err = await c.addVillage(n);
                      if (!mounted) return;
                      showSnack(context, err ?? 'Village "$n" added', error: err != null);
                    },
              icon: const Icon(Icons.add_circle_rounded, color: AppColors.green),
            ),
          ),
          const SizedBox(height: 6),
          _villageTile(c, null, 'All villages', c.pdfs.length, null),
          if (c.unassignedPdfs > 0) _villageTile(c, '', 'Unassigned', c.unassignedPdfs, null),
          const Divider(height: 10),
          if (c.villages.isEmpty)
            const Padding(padding: EdgeInsets.all(12), child: Text('No villages yet. Add one or upload a PDF.', style: TextStyle(color: AppColors.textMuted, fontSize: 13)))
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 520),
              child: ListView(
                shrinkWrap: true,
                children: [for (final v in c.villages) _villageTile(c, v.name, v.name, v.pdfs, v)],
              ),
            ),
        ],
      ),
    );
  }

  Widget _villageTile(AdminController c, String? filter, String label, int count, Village? v) {
    final selected = c.villageFilter == filter;
    return InkWell(
      onTap: () => c.setVillageFilter(filter),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(color: selected ? AppColors.greenLight : null, borderRadius: BorderRadius.circular(8)),
        child: Row(
          children: [
            Icon(
              filter == null ? Icons.public_rounded : (filter.isEmpty ? Icons.folder_off_outlined : Icons.folder_rounded),
              size: 18,
              color: selected ? AppColors.green : AppColors.textMuted,
            ),
            const SizedBox(width: 8),
            Expanded(child: Text(label, overflow: TextOverflow.ellipsis, style: TextStyle(fontWeight: selected ? FontWeight.w800 : FontWeight.w600, fontSize: 13.5, color: selected ? AppColors.green : AppColors.textPrimary))),
            Pill(label: '$count', color: selected ? Colors.white : AppColors.surface, textColor: AppColors.textSecondary),
            if (v != null)
              PopupMenuButton<String>(
                padding: EdgeInsets.zero,
                iconSize: 18,
                onSelected: (a) => _villageMenu(c, v, a),
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'upload', child: ListTile(dense: true, leading: Icon(Icons.upload_file_rounded), title: Text('Upload PDFs here'))),
                  PopupMenuItem(value: 'rename', child: ListTile(dense: true, leading: Icon(Icons.edit_rounded), title: Text('Rename'))),
                  PopupMenuItem(value: 'delete', child: ListTile(dense: true, leading: Icon(Icons.delete_outline_rounded, color: AppColors.danger), title: Text('Delete', style: TextStyle(color: AppColors.danger)))),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _pdfCard(AdminController c) {
    final title = c.villageFilter == null ? 'All PDFs' : (c.villageFilter!.isEmpty ? 'Unassigned PDFs' : 'PDFs · ${c.villageFilter}');
    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 10,
            runSpacing: 10,
            children: [
              SectionTitle(icon: Icons.picture_as_pdf_rounded, title: '$title (${c.pdfs.length})'),
              SizedBox(
                width: 260,
                child: TextField(
                  controller: _search,
                  onChanged: c.setPdfQuery,
                  decoration: InputDecoration(
                    hintText: 'Search PDFs...',
                    isDense: true,
                    prefixIcon: const Icon(Icons.search_rounded, size: 20),
                    suffixIcon: _search.text.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.close_rounded, size: 18),
                            onPressed: () {
                              _search.clear();
                              c.setPdfQuery('');
                            },
                          ),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          PdfTable(pdfs: c.pdfs, onAction: (p, a) => _onPdfAction(c, p, a)),
        ],
      ),
    );
  }
}
