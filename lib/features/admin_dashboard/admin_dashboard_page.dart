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
  bool _showDuplicates = false;
  int _duplicateSection = 0;
  bool _sameRelativeAcrossVillages = true;
  Future<DuplicateOverview>? _duplicatesFuture;
  String? _duplicateIndexSignature;

  String _indexSignature(AdminController c) =>
      '${c.index?.version}:${c.index?.indexedPdfs}:${c.index?.totalRecords}';

  void _selectDuplicates() {
    setState(() {
      _showDuplicates = true;
      _duplicateIndexSignature = _indexSignature(
        context.read<AdminController>(),
      );
      _duplicatesFuture = context.read<ApiClient>().adminDuplicates();
    });
  }

  void _refresh(AdminController c) {
    c.refresh();
    if (_showDuplicates) {
      setState(
        () => _duplicatesFuture = context.read<ApiClient>().adminDuplicates(),
      );
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _upload(AdminController c, {String? village}) async {
    final sel = await showUploadDialog(
      context,
      c.villages,
      initialVillage: village ?? c.villageFilter,
    );
    if (sel == null || !mounted) return;
    showSnack(
      context,
      'Uploading ${sel.files.length} file(s) to ${sel.village}...',
    );
    final r = await c.upload(sel.files, sel.village);
    if (!mounted) return;
    if (r.errors.isNotEmpty) {
      showSnack(
        context,
        '${r.saved} uploaded, ${r.errors.length} failed:\n${r.errors.join('\n')}',
        error: true,
      );
    } else {
      showSnack(
        context,
        '${r.saved} PDF(s) uploaded to ${sel.village}. Indexing started.',
      );
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
      case PdfAction.retry:
        err = await c.retryPdf(p.id);
        if (err == null && mounted) {
          showSnack(context, '${p.name} queued for indexing.');
        }
      case PdfAction.replace:
        final files = await pickPdfs(multiple: false);
        if (files.isEmpty) return;
        err = await c.replacePdf(p.id, files.first.name, files.first.bytes);
        if (err == null && mounted) {
          showSnack(context, '${p.name} replaced. Re-indexing.');
        }
      case PdfAction.rename:
        final name = await showTextDialog(
          context,
          title: 'Rename PDF',
          label: 'New file name',
          initial: p.name,
        );
        if (name == null || name.isEmpty || name == p.name) return;
        err = await c.renamePdf(p.id, name);
        if (err == null && mounted) showSnack(context, 'Renamed to $name');
      case PdfAction.move:
        final v = await showVillagePicker(
          context,
          c.villages,
          current: p.village,
        );
        if (v == null || v == p.village) return;
        err = await c.movePdf(p.id, v);
        if (err == null && mounted) showSnack(context, '${p.name} moved to $v');
      case PdfAction.delete:
        final ok = await showConfirmDialog(
          context,
          title: 'Delete PDF?',
          message:
              '"${p.id}" will be permanently removed from storage and from the search index.',
        );
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
        final n = await showTextDialog(
          context,
          title: 'Rename village',
          label: 'Village name',
          initial: v.name,
        );
        if (n == null || n.isEmpty || n == v.name) return;
        err = await c.renameVillage(v.name, n);
      case 'delete':
        final ok = await showConfirmDialog(
          context,
          title: 'Delete village?',
          message: v.pdfs == 0
              ? 'Remove "${v.name}" from the list?'
              : '"${v.name}" and its ${v.pdfs} PDF(s) will be permanently deleted and removed from the index.',
        );
        if (!ok) return;
        err = await c.deleteVillage(v.name);
    }
    if (err != null && mounted) showSnack(context, err, error: true);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.watch<AdminController>();
    if (_showDuplicates) {
      final signature = _indexSignature(c);
      if (_duplicateIndexSignature != signature) {
        _duplicateIndexSignature = signature;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted && _showDuplicates) {
            setState(
              () => _duplicatesFuture = context
                  .read<ApiClient>()
                  .adminDuplicates(),
            );
          }
        });
      }
    }
    final wide = MediaQuery.sizeOf(context).width >= 980;
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: AppColors.navy,
        foregroundColor: Colors.white,
        title: Row(
          children: [
            const Icon(Icons.admin_panel_settings_rounded),
            const SizedBox(width: 8),
            Text(
              wide ? 'Voter Finder · Admin' : 'Admin',
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ],
        ),
        actions: [
          if (wide)
            TextButton.icon(
              onPressed: () => Navigator.of(context).pushReplacementNamed('/'),
              icon: const Icon(
                Icons.public_rounded,
                color: Colors.white70,
                size: 18,
              ),
              label: const Text(
                'User site',
                style: TextStyle(color: Colors.white70),
              ),
            )
          else
            IconButton(
              tooltip: 'User site',
              onPressed: () => Navigator.of(context).pushReplacementNamed('/'),
              icon: const Icon(Icons.public_rounded, color: Colors.white70),
            ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: c.loading ? null : () => _refresh(c),
            icon: const Icon(Icons.refresh_rounded),
          ),
          const SizedBox(width: 6),
        ],
        bottom: c.busy
            ? const PreferredSize(
                preferredSize: Size.fromHeight(3),
                child: LinearProgressIndicator(
                  minHeight: 3,
                  color: AppColors.saffron,
                  backgroundColor: AppColors.navy,
                ),
              )
            : null,
      ),
      floatingActionButton: _showDuplicates
          ? null
          : FloatingActionButton.extended(
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
                      Wrap(
                        spacing: 8,
                        children: [
                          ChoiceChip(
                            label: const Text('Dashboard'),
                            avatar: const Icon(
                              Icons.dashboard_rounded,
                              size: 18,
                            ),
                            selected: !_showDuplicates,
                            onSelected: (_) =>
                                setState(() => _showDuplicates = false),
                          ),
                          ChoiceChip(
                            label: const Text('Duplicates'),
                            avatar: const Icon(
                              Icons.content_copy_rounded,
                              size: 18,
                            ),
                            selected: _showDuplicates,
                            onSelected: (_) => _selectDuplicates(),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      if (_showDuplicates)
                        _duplicatesCard()
                      else ...[
                        IndexStatusCard(
                          status: c.index,
                          busy: c.busy,
                          onRebuild: () async {
                            final err = await c.rebuild();
                            if (!context.mounted) return;
                            showSnack(
                              context,
                              err ?? 'Full index rebuild started',
                              error: err != null,
                            );
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
                    ],
                  ),
                ),
              ),
      ),
    );
  }

  Widget _duplicatesCard() {
    return AppCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SectionTitle(
            icon: Icons.content_copy_rounded,
            title: 'Duplicate review',
          ),
          const SizedBox(height: 8),
          const Text(
            'These voters remain searchable. This page only groups possible repeats; it never merges or removes records.',
            style: TextStyle(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ChoiceChip(
                label: const Text('Same EPIC'),
                selected: _duplicateSection == 0,
                onSelected: (_) => setState(() => _duplicateSection = 0),
              ),
              ChoiceChip(
                label: const Text('Same name + relative (one village)'),
                selected: _duplicateSection == 1,
                onSelected: (_) => setState(() => _duplicateSection = 1),
              ),
              ChoiceChip(
                label: const Text('Same name across villages'),
                selected: _duplicateSection == 2,
                onSelected: (_) => setState(() => _duplicateSection = 2),
              ),
            ],
          ),
          if (_duplicateSection == 2) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(
                  label: const Text('Same relative'),
                  selected: _sameRelativeAcrossVillages,
                  onSelected: (_) =>
                      setState(() => _sameRelativeAcrossVillages = true),
                ),
                ChoiceChip(
                  label: const Text('Different relative'),
                  selected: !_sameRelativeAcrossVillages,
                  onSelected: (_) =>
                      setState(() => _sameRelativeAcrossVillages = false),
                ),
              ],
            ),
          ],
          const SizedBox(height: 12),
          FutureBuilder<DuplicateOverview>(
            future: _duplicatesFuture,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: CircularProgressIndicator()),
                );
              }
              if (snapshot.hasError) {
                return Text(
                  'Could not load duplicates: ${snapshot.error}',
                  style: const TextStyle(color: AppColors.danger),
                );
              }
              final overview = snapshot.data!;
              if (_duplicateSection == 2 &&
                  overview.crossVillageSetupRequired) {
                return const Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'Cross-village review needs database migration 0005_cross_village_duplicates.sql. Run it in Supabase SQL Editor, then refresh this page.',
                  ),
                );
              }
              final groups = switch (_duplicateSection) {
                0 => overview.epic,
                1 => overview.name,
                _ =>
                  _sameRelativeAcrossVillages
                      ? overview.sameRelativeAcrossVillages
                      : overview.differentRelativeAcrossVillages,
              };
              final records = groups.fold<int>(
                0,
                (total, group) => total + group.records.length,
              );
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '${groups.length} matching groups · $records voter records',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  if (_duplicateSection == 2) ...[
                    const SizedBox(height: 4),
                    Text(
                      _sameRelativeAcrossVillages
                          ? 'Same full name and relative name in different villages.'
                          : 'Same full name in different villages, with different relative names. Review manually; a name may appear in both cross-village sections.',
                      style: const TextStyle(color: AppColors.textSecondary),
                    ),
                  ],
                  const SizedBox(height: 10),
                  if (groups.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(20),
                      child: Text('No matching records found.'),
                    )
                  else
                    for (final group in groups) _duplicateGroup(group),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _duplicateGroup(DuplicateGroup group) {
    return Card(
      key: ValueKey(
        '$_duplicateSection:$_sameRelativeAcrossVillages:${group.key}',
      ),
      margin: const EdgeInsets.only(bottom: 8),
      child: ExpansionTile(
        title: Text(
          group.label,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          _duplicateSection == 0
              ? '${group.records.length} records with this EPIC'
              : '${group.relationLabel.isEmpty ? "Different relatives" : group.relationLabel} · '
                    '${_duplicateSection == 1 ? group.records.first.village : "Multiple villages"} · '
                    '${group.records.length} possible matches',
        ),
        children: [
          for (final record in group.records)
            ListTile(
              isThreeLine: true,
              title: Text(record.name),
              subtitle: Text(
                '${record.relationName}\n${record.village} · EPIC ${record.epic.isEmpty ? "—" : record.epic} · Serial ${record.serial.isEmpty ? "—" : record.serial}\n${record.pdfName} · Page ${record.page}',
              ),
              trailing: IconButton(
                tooltip: 'Open PDF at this voter',
                icon: const Icon(Icons.open_in_new_rounded),
                onPressed: () => context.read<PdfViewer>().open(
                  context,
                  record.pdf,
                  page: record.page,
                  voterId: record.id,
                ),
              ),
            ),
        ],
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
                      final n = await showTextDialog(
                        context,
                        title: 'Add village',
                        label: 'Village name',
                        confirm: 'Add',
                        icon: Icons.add_location_alt_rounded,
                      );
                      if (n == null || n.isEmpty) return;
                      final err = await c.addVillage(n);
                      if (!mounted) return;
                      showSnack(
                        context,
                        err ?? 'Village "$n" added',
                        error: err != null,
                      );
                    },
              icon: const Icon(
                Icons.add_circle_rounded,
                color: AppColors.green,
              ),
            ),
          ),
          const SizedBox(height: 6),
          _villageTile(c, null, 'All villages', c.pdfs.length, null),
          if (c.unassignedPdfs > 0)
            _villageTile(c, '', 'Unassigned', c.unassignedPdfs, null),
          const Divider(height: 10),
          if (c.villages.isEmpty)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'No villages yet. Add one or upload a PDF.',
                style: TextStyle(color: AppColors.textMuted, fontSize: 13),
              ),
            )
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 520),
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final v in c.villages)
                    _villageTile(c, v.name, v.name, v.pdfs, v),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _villageTile(
    AdminController c,
    String? filter,
    String label,
    int count,
    Village? v,
  ) {
    final selected = c.villageFilter == filter;
    return InkWell(
      onTap: () => c.setVillageFilter(filter),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? AppColors.greenLight : null,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            Icon(
              filter == null
                  ? Icons.public_rounded
                  : (filter.isEmpty
                        ? Icons.folder_off_outlined
                        : Icons.folder_rounded),
              size: 18,
              color: selected ? AppColors.green : AppColors.textMuted,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
                  fontSize: 13.5,
                  color: selected ? AppColors.green : AppColors.textPrimary,
                ),
              ),
            ),
            Pill(
              label: '$count',
              color: selected ? Colors.white : AppColors.surface,
              textColor: AppColors.textSecondary,
            ),
            if (v != null)
              PopupMenuButton<String>(
                padding: EdgeInsets.zero,
                iconSize: 18,
                onSelected: (a) => _villageMenu(c, v, a),
                itemBuilder: (_) => const [
                  PopupMenuItem(
                    value: 'upload',
                    child: ListTile(
                      dense: true,
                      leading: Icon(Icons.upload_file_rounded),
                      title: Text('Upload PDFs here'),
                    ),
                  ),
                  PopupMenuItem(
                    value: 'rename',
                    child: ListTile(
                      dense: true,
                      leading: Icon(Icons.edit_rounded),
                      title: Text('Rename'),
                    ),
                  ),
                  PopupMenuItem(
                    value: 'delete',
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
        ),
      ),
    );
  }

  Widget _pdfCard(AdminController c) {
    final title = c.villageFilter == null
        ? 'All PDFs'
        : (c.villageFilter!.isEmpty
              ? 'Unassigned PDFs'
              : 'PDFs · ${c.villageFilter}');
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
              SectionTitle(
                icon: Icons.picture_as_pdf_rounded,
                title: '$title (${c.pdfs.length})',
              ),
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
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
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
