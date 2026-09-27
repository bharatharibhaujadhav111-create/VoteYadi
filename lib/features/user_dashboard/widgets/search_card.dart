import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common_widgets.dart';
import '../search_controller.dart';

/// "नाव शोधा" card: village dropdown + search input + suggestions + recents.
class SearchCard extends StatefulWidget {
  const SearchCard({super.key});

  @override
  State<SearchCard> createState() => _SearchCardState();
}

class _SearchCardState extends State<SearchCard> {
  final _text = TextEditingController();
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(() {
      if (!_focus.hasFocus) {
        // small delay so a tap on a suggestion registers before hiding
        Future.delayed(const Duration(milliseconds: 150), () {
          if (mounted && !_focus.hasFocus) context.read<VoterSearchController>().clearSuggestions();
        });
      } else {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _submit(String q) {
    final c = context.read<VoterSearchController>();
    _text.text = q;
    _text.selection = TextSelection.collapsed(offset: q.length);
    _focus.unfocus();
    c.search(q);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.watch<VoterSearchController>();
    final narrow = MediaQuery.sizeOf(context).width < 600;
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SectionTitle(icon: Icons.search_rounded, title: 'नाव शोधा', center: true),
          const SizedBox(height: 4),
          const Text(
            'मतदाराचे नाव मराठीत किंवा English मध्ये टाका आणि यादीत शोधा',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12.5, color: AppColors.textSecondary),
          ),
          const SizedBox(height: 14),
          _VillageDropdown(villages: c.villages, value: c.selectedVillage, onChanged: c.selectVillage),
          const SizedBox(height: 10),
          if (narrow) ...[
            _input(c),
            const SizedBox(height: 10),
            SizedBox(height: 50, child: _button(c)),
          ] else
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: _input(c)),
                const SizedBox(width: 10),
                SizedBox(height: 52, child: _button(c)),
              ],
            ),
          if (c.suggestions.isNotEmpty && _focus.hasFocus) _Suggestions(items: c.suggestions, query: _text.text, onTap: _submit),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Icon(Icons.verified_rounded, size: 15, color: AppColors.green),
              SizedBox(width: 5),
              Text('शोध पूर्णपणे मोफत आहे', style: TextStyle(fontSize: 12, color: AppColors.green, fontWeight: FontWeight.w700)),
            ],
          ),
          if (c.recent.isNotEmpty && c.response == null && !c.loading) ...[
            const SizedBox(height: 12),
            _Recent(items: c.recent, onTap: _submit, onRemove: c.removeRecent, onClear: c.clearRecent),
          ],
        ],
      ),
    );
  }

  Widget _input(VoterSearchController c) {
    return TextField(
      controller: _text,
      focusNode: _focus,
      textInputAction: TextInputAction.search,
      onChanged: c.onQueryChanged,
      onSubmitted: _submit,
      style: const TextStyle(fontSize: 15),
      decoration: InputDecoration(
        hintText: 'उदा. विजयसिंह जाधव किंवा Vijaysinh Jadhav',
        prefixIcon: const Icon(Icons.person_search_rounded, color: AppColors.textMuted),
        suffixIcon: _text.text.isEmpty
            ? null
            : IconButton(
                icon: const Icon(Icons.close_rounded, size: 20),
                onPressed: () {
                  _text.clear();
                  c.clear();
                  setState(() {});
                },
              ),
      ),
    );
  }

  Widget _button(VoterSearchController c) {
    return ElevatedButton.icon(
      onPressed: c.loading ? null : () => _submit(_text.text),
      icon: c.loading
          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
          : const Icon(Icons.search_rounded, size: 22),
      label: const Text('शोधा', style: TextStyle(fontSize: 16)),
    );
  }
}

class _VillageDropdown extends StatelessWidget {
  const _VillageDropdown({required this.villages, required this.value, required this.onChanged});
  final List<Village> villages;
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final items = <DropdownMenuItem<String>>[
      const DropdownMenuItem(value: '', child: Text('सर्व गावे (संपूर्ण मतदार यादी)')),
      ...villages.map(
        (v) => DropdownMenuItem(
          value: v.name,
          child: Row(
            children: [
              Expanded(child: Text(v.name, overflow: TextOverflow.ellipsis)),
              if (v.records > 0)
                Text('${v.records}', style: const TextStyle(fontSize: 12, color: AppColors.textMuted))
              else
                const Text('यादी नाही', style: TextStyle(fontSize: 11, color: AppColors.textMuted)),
            ],
          ),
        ),
      ),
    ];
    return DropdownButtonFormField<String>(
      initialValue: villages.any((v) => v.name == value) ? value : '',
      items: items,
      isExpanded: true,
      onChanged: (v) => onChanged(v ?? ''),
      selectedItemBuilder: (context) => [
        const Text('सर्व गावे (संपूर्ण मतदार यादी)', overflow: TextOverflow.ellipsis),
        ...villages.map((v) => Text(v.name, overflow: TextOverflow.ellipsis)),
      ],
      decoration: const InputDecoration(
        labelText: 'गाव निवडा',
        prefixIcon: Icon(Icons.location_on_rounded, color: AppColors.green),
        contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      ),
    );
  }
}

class _Suggestions extends StatelessWidget {
  const _Suggestions({required this.items, required this.query, required this.onTap});
  final List<Suggestion> items;
  final String query;
  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 6),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
        boxShadow: const [BoxShadow(color: Color(0x14000000), blurRadius: 12, offset: Offset(0, 6))],
      ),
      child: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            color: AppColors.surface,
            child: Text(
              'यादीतील जुळणारी नावे  ·  ${items.length}',
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.textMuted),
            ),
          ),
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) const Divider(height: 1),
            InkWell(
              onTap: () => onTap(items[i].text),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                child: Row(
                  children: [
                    Container(
                      width: 30,
                      height: 30,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: AppColors.saffronLight, borderRadius: BorderRadius.circular(8)),
                      child: Text(
                        items[i].text.isNotEmpty ? items[i].text[0].toUpperCase() : '?',
                        style: const TextStyle(fontWeight: FontWeight.w900, color: AppColors.saffronDark, fontSize: 13),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _Highlighted(text: items[i].text, query: query),
                          if (items[i].relationName.isNotEmpty || items[i].village.isNotEmpty)
                            Text(
                              [
                                if (items[i].relationName.isNotEmpty) '${_relLabel(items[i].relationType)}: ${_title(items[i].relationName)}',
                                if (items[i].village.isNotEmpty) items[i].village,
                                if (items[i].page > 0 && items[i].pdf.isNotEmpty) 'पान ${items[i].page}',
                              ].join('  ·  '),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.north_west_rounded, size: 15, color: AppColors.textMuted),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  static String _relLabel(String t) {
    switch (t.toLowerCase()) {
      case 'husband':
        return 'पती';
      case 'mother':
        return 'आई';
      default:
        return 'वडील';
    }
  }

  static String _title(String s) {
    if (s != s.toUpperCase()) return s;
    return s.split(' ').map((w) => w.isEmpty ? w : w[0] + w.substring(1).toLowerCase()).join(' ');
  }
}

/// Renders [text] with the typed [query] tokens in bold saffron.
class _Highlighted extends StatelessWidget {
  const _Highlighted({required this.text, required this.query});
  final String text;
  final String query;

  @override
  Widget build(BuildContext context) {
    final tokens = query.toLowerCase().split(RegExp(r'\s+')).where((t) => t.length >= 2).toList();
    const base = TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: AppColors.navyText);
    const hit = TextStyle(fontSize: 14.5, fontWeight: FontWeight.w900, color: AppColors.saffronDark);
    if (tokens.isEmpty) return Text(text, maxLines: 1, overflow: TextOverflow.ellipsis, style: base);
    final spans = <TextSpan>[];
    for (final word in text.split(' ')) {
      final lw = word.toLowerCase();
      final match = tokens.firstWhere((t) => lw.startsWith(t), orElse: () => '');
      if (match.isEmpty) {
        spans.add(TextSpan(text: '$word ', style: base));
      } else {
        spans.add(TextSpan(text: word.substring(0, match.length), style: hit));
        spans.add(TextSpan(text: '${word.substring(match.length)} ', style: base));
      }
    }
    return Text.rich(TextSpan(children: spans), maxLines: 1, overflow: TextOverflow.ellipsis);
  }
}

class _Recent extends StatelessWidget {
  const _Recent({required this.items, required this.onTap, required this.onRemove, required this.onClear});
  final List<String> items;
  final ValueChanged<String> onTap;
  final ValueChanged<String> onRemove;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.history_rounded, size: 16, color: AppColors.textSecondary),
            const SizedBox(width: 6),
            const Text('अलीकडील शोध', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: AppColors.textSecondary)),
            const Spacer(),
            TextButton(onPressed: onClear, child: const Text('साफ करा', style: TextStyle(fontSize: 12))),
          ],
        ),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final r in items)
              InputChip(
                label: Text(r),
                onPressed: () => onTap(r),
                onDeleted: () => onRemove(r),
                deleteIconColor: AppColors.textMuted,
              ),
          ],
        ),
      ],
    );
  }
}
