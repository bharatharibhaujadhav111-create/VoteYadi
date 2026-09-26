import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';

/// Result of the upload dialog: chosen village + files.
class UploadSelection {
  const UploadSelection({required this.village, required this.files});
  final String village;
  final List<({String name, Uint8List bytes})> files;
}

Future<List<({String name, Uint8List bytes})>> pickPdfs({bool multiple = true}) async {
  final res = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['pdf'], allowMultiple: multiple, withData: true);
  if (res == null) return const [];
  return [
    for (final f in res.files)
      if (f.bytes != null) (name: f.name, bytes: f.bytes!),
  ];
}

/// Upload dialog: pick a village from the dropdown (or add a new one), then
/// choose one or many PDF files.
Future<UploadSelection?> showUploadDialog(BuildContext context, List<Village> villages, {String? initialVillage}) {
  return showDialog<UploadSelection>(
    context: context,
    builder: (ctx) => _UploadDialog(villages: villages, initialVillage: initialVillage),
  );
}

class _UploadDialog extends StatefulWidget {
  const _UploadDialog({required this.villages, this.initialVillage});
  final List<Village> villages;
  final String? initialVillage;

  @override
  State<_UploadDialog> createState() => _UploadDialogState();
}

class _UploadDialogState extends State<_UploadDialog> {
  static const _newVillage = '__new__';
  late String _village;
  final _newName = TextEditingController();
  List<({String name, Uint8List bytes})> _files = const [];
  String? _err;

  @override
  void initState() {
    super.initState();
    _village = widget.initialVillage != null && widget.villages.any((v) => v.name == widget.initialVillage)
        ? widget.initialVillage!
        : (widget.villages.isNotEmpty ? widget.villages.first.name : _newVillage);
  }

  @override
  void dispose() {
    _newName.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final files = await pickPdfs();
    if (files.isNotEmpty) setState(() => _files = [..._files, ...files]);
  }

  void _submit() {
    final village = _village == _newVillage ? _newName.text.trim() : _village;
    if (village.isEmpty) {
      setState(() => _err = 'Please select or enter a village name');
      return;
    }
    if (_files.isEmpty) {
      setState(() => _err = 'Please choose at least one PDF file');
      return;
    }
    Navigator.of(context).pop(UploadSelection(village: village, files: _files));
  }

  @override
  Widget build(BuildContext context) {
    final total = _files.fold<int>(0, (a, f) => a + f.bytes.length);
    return AlertDialog(
      title: const Row(children: [Icon(Icons.upload_file_rounded, color: AppColors.saffron), SizedBox(width: 8), Text('Upload PDFs')]),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Step 1 · Select village', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: AppColors.textSecondary)),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: _village,
                isExpanded: true,
                items: [
                  for (final v in widget.villages)
                    DropdownMenuItem(
                      value: v.name,
                      child: Row(children: [
                        Expanded(child: Text(v.name, overflow: TextOverflow.ellipsis)),
                        Text('${v.pdfs} PDF', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                      ]),
                    ),
                  const DropdownMenuItem(
                    value: _newVillage,
                    child: Row(children: [Icon(Icons.add_location_alt_rounded, size: 18, color: AppColors.green), SizedBox(width: 8), Text('Add new village...')]),
                  ),
                ],
                onChanged: (v) => setState(() => _village = v ?? _village),
                decoration: const InputDecoration(prefixIcon: Icon(Icons.location_on_rounded, color: AppColors.green), contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12)),
              ),
              if (_village == _newVillage) ...[
                const SizedBox(height: 10),
                TextField(
                  controller: _newName,
                  autofocus: true,
                  decoration: const InputDecoration(labelText: 'New village name', hintText: 'e.g. Tirhe / तिर्हे', contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12)),
                ),
              ],
              const SizedBox(height: 18),
              const Text('Step 2 · Choose PDF files', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: AppColors.textSecondary)),
              const SizedBox(height: 8),
              InkWell(
                onTap: _pick,
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 22),
                  decoration: BoxDecoration(
                    color: AppColors.saffronLight,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFFFC9A6), width: 1.4),
                  ),
                  child: Column(children: [
                    const Icon(Icons.cloud_upload_rounded, size: 36, color: AppColors.saffron),
                    const SizedBox(height: 6),
                    Text(_files.isEmpty ? 'Click to choose PDF files' : 'Add more files', style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.saffronDark)),
                    const Text('Multiple files supported', style: TextStyle(fontSize: 11.5, color: AppColors.textMuted)),
                  ]),
                ),
              ),
              if (_files.isNotEmpty) ...[
                const SizedBox(height: 10),
                Container(
                  constraints: const BoxConstraints(maxHeight: 180),
                  decoration: BoxDecoration(border: Border.all(color: AppColors.border), borderRadius: BorderRadius.circular(10)),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: _files.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final f = _files[i];
                      return ListTile(
                        dense: true,
                        leading: const Icon(Icons.picture_as_pdf_rounded, color: AppColors.saffron, size: 20),
                        title: Text(f.name, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13)),
                        subtitle: Text('${(f.bytes.length / (1024 * 1024)).toStringAsFixed(2)} MB', style: const TextStyle(fontSize: 11)),
                        trailing: IconButton(
                          icon: const Icon(Icons.close_rounded, size: 18),
                          onPressed: () => setState(() => _files = [..._files]..removeAt(i)),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 6),
                Text('${_files.length} file(s) · ${(total / (1024 * 1024)).toStringAsFixed(2)} MB', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
              ],
              if (_err != null) ...[
                const SizedBox(height: 10),
                Text(_err!, style: const TextStyle(color: AppColors.danger, fontSize: 12.5)),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel', style: TextStyle(color: AppColors.textSecondary))),
        ElevatedButton.icon(onPressed: _submit, icon: const Icon(Icons.upload_rounded, size: 18), label: Text(_files.isEmpty ? 'Upload' : 'Upload ${_files.length} file(s)')),
      ],
    );
  }
}

Future<String?> showTextDialog(BuildContext context, {required String title, required String label, String initial = '', String confirm = 'Save', IconData icon = Icons.edit_rounded}) {
  final ctrl = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Row(children: [Icon(icon, color: AppColors.saffron), const SizedBox(width: 8), Text(title)]),
      content: SizedBox(
        width: 400,
        child: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: InputDecoration(labelText: label),
          onSubmitted: (v) => Navigator.of(ctx).pop(v.trim()),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel', style: TextStyle(color: AppColors.textSecondary))),
        ElevatedButton(onPressed: () => Navigator.of(ctx).pop(ctrl.text.trim()), child: Text(confirm)),
      ],
    ),
  );
}

Future<bool> showConfirmDialog(BuildContext context, {required String title, required String message, String confirm = 'Delete'}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Row(children: [const Icon(Icons.warning_amber_rounded, color: AppColors.danger), const SizedBox(width: 8), Text(title)]),
      content: SizedBox(width: 400, child: Text(message)),
      actions: [
        TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel', style: TextStyle(color: AppColors.textSecondary))),
        ElevatedButton(
          style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
          onPressed: () => Navigator.of(ctx).pop(true),
          child: Text(confirm),
        ),
      ],
    ),
  );
  return r ?? false;
}

Future<String?> showVillagePicker(BuildContext context, List<Village> villages, {String? current}) {
  return showDialog<String>(
    context: context,
    builder: (ctx) => SimpleDialog(
      title: const Text('Move to village'),
      children: [
        for (final v in villages)
          SimpleDialogOption(
            onPressed: () => Navigator.of(ctx).pop(v.name),
            child: Row(children: [
              Icon(v.name == current ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded, size: 18, color: v.name == current ? AppColors.green : AppColors.textMuted),
              const SizedBox(width: 10),
              Expanded(child: Text(v.name)),
              Text('${v.pdfs} PDF', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
            ]),
          ),
      ],
    ),
  );
}
