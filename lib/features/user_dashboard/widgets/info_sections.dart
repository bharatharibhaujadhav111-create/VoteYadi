import 'package:flutter/material.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/common_widgets.dart';
import 'hero_header.dart';

/// Stats row: villages / parts / voters / SIR updated.
class StatsRow extends StatelessWidget {
  const StatsRow({required this.stats, super.key});
  final PublicStats? stats;

  @override
  Widget build(BuildContext context) {
    final s = stats;
    final items = [
      _Stat(icon: Icons.groups_rounded, color: AppColors.green, value: s == null ? '—' : '${s.totalVillages}', label: 'गावे', sub: 'उत्तर सोलापूरतील'),
      _Stat(icon: Icons.description_rounded, color: AppColors.blue, value: s == null ? '—' : '${s.totalPdfs}', label: 'मतदार यादी Booth', sub: 'PDF फाईल्स'),
      _Stat(icon: Icons.people_alt_rounded, color: AppColors.purple, value: s == null ? '—' : Formatters.countPlus(s.totalRecords), label: 'एकूण मतदार', sub: 'इंडेक्स केलेले'),
      const _Stat(icon: Icons.check_circle_rounded, color: AppColors.saffron, value: 'सही व अद्यावत', label: 'SIR नंतरची यादी', sub: '', small: true),
    ];
    return LayoutBuilder(
      builder: (context, c) {
        final cols = c.maxWidth < 520 ? 2 : 4;
        final w = (c.maxWidth - (cols - 1) * 10) / cols;
        return Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [for (final i in items) SizedBox(width: w, child: i)],
        );
      },
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.icon, required this.color, required this.value, required this.label, required this.sub, this.small = false});
  final IconData icon;
  final Color color;
  final String value;
  final String label;
  final String sub;
  final bool small;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
      child: Column(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(10)),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(height: 8),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(value, style: TextStyle(fontSize: small ? 14 : 24, fontWeight: FontWeight.w900, color: color, height: 1.1)),
          ),
          const SizedBox(height: 4),
          Text(label, textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.navyText)),
          if (sub.isNotEmpty) Text(sub, textAlign: TextAlign.center, style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted)),
        ],
      ),
    );
  }
}

/// "समाविष्ट गावे" card with chips; tapping a chip selects that village.
class VillagesCard extends StatefulWidget {
  const VillagesCard({required this.villages, required this.selected, required this.onSelect, super.key});
  final List<Village> villages;
  final String selected;
  final ValueChanged<String> onSelect;

  @override
  State<VillagesCard> createState() => _VillagesCardState();
}

class _VillagesCardState extends State<VillagesCard> {
  bool _all = false;

  @override
  Widget build(BuildContext context) {
    final list = _all ? widget.villages : widget.villages.take(14).toList();
    final more = widget.villages.length - list.length;
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionTitle(
            icon: Icons.location_on_rounded,
            iconColor: AppColors.green,
            title: 'समाविष्ट गावे (${widget.villages.length})',
            trailing: TextButton(
              onPressed: () => setState(() => _all = !_all),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(_all ? 'कमी दाखवा' : 'संपूर्ण यादी पहा', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700)),
                  Icon(_all ? Icons.expand_less_rounded : Icons.arrow_forward_rounded, size: 16),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          if (widget.villages.isEmpty)
            const Text('अद्याप गावे जोडलेली नाहीत.', style: TextStyle(color: AppColors.textMuted))
          else
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final v in list)
                  ChoiceChip(
                    label: Text(v.name),
                    selected: widget.selected == v.name,
                    selectedColor: AppColors.greenLight,
                    labelStyle: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: widget.selected == v.name ? AppColors.green : AppColors.textPrimary,
                    ),
                    avatar: v.records == 0 ? const Icon(Icons.hourglass_empty_rounded, size: 13, color: AppColors.textMuted) : null,
                    onSelected: (_) => widget.onSelect(widget.selected == v.name ? '' : v.name),
                  ),
                if (!_all && more > 0)
                  ActionChip(
                    label: Text('आणि इतर $more...'),
                    labelStyle: const TextStyle(fontSize: 12.5, color: AppColors.textSecondary),
                    onPressed: () => setState(() => _all = true),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

/// "नाव कसे शोधाल?" guidance card.
class HowToCard extends StatelessWidget {
  const HowToCard({super.key});

  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.person_outline_rounded, 'पूर्ण नाव टाका', 'उदा. विजयसिंह जाधव'),
      (Icons.people_outline_rounded, 'वडिलांचे / पतीचे नाव टाका', 'उदा. भारत हरिभाऊ जाधव'),
      (Icons.search_rounded, 'अचूक किंवा साधारण नाव चालेल', 'स्पेलिंग वेगवेगळे असले तरी चालेल'),
    ];
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('नाव कसे शोधाल?', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navyText)),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, c) {
              final horizontal = c.maxWidth >= 640;
              final children = [
                for (final it in items)
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 30,
                        height: 30,
                        decoration: BoxDecoration(color: AppColors.greenLight, borderRadius: BorderRadius.circular(8)),
                        child: Icon(it.$1, size: 17, color: AppColors.green),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(it.$2, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: AppColors.navyText)),
                            Text(it.$3, style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted)),
                          ],
                        ),
                      ),
                    ],
                  ),
              ];
              if (horizontal) {
                return Row(children: [for (final ch in children) Expanded(child: ch)]);
              }
              return Column(
                children: [
                  for (var i = 0; i < children.length; i++) ...[
                    children[i],
                    if (i < children.length - 1) const SizedBox(height: 10),
                  ],
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

/// Footer band with Bharat Jadhav + slogan, then the dark strip.
class FooterBand extends StatelessWidget {
  const FooterBand({super.key});

  @override
  Widget build(BuildContext context) {
    final narrow = MediaQuery.sizeOf(context).width < 640;
    final leader = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 74,
          height: 74,
          padding: const EdgeInsets.all(3),
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(colors: [AppColors.green, Colors.white, AppColors.saffron], begin: Alignment.topLeft, end: Alignment.bottomRight),
          ),
          child: ClipOval(child: Image.asset('assets/images/bharat_jadhav.jpg', fit: BoxFit.cover, alignment: Alignment.topCenter)),
        ),
        const SizedBox(width: 12),
        const Flexible(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('भारत जाधव', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: AppColors.navyText)),
              Text('अध्यक्ष', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.saffronDark)),
              Text('उत्तर सोलापूर काँग्रेस', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.green)),
            ],
          ),
        ),
      ],
    );
    final slogan = Column(
      crossAxisAlignment: narrow ? CrossAxisAlignment.center : CrossAxisAlignment.end,
      children: [
        Text(
          'उत्तर सोलापूरतील नागरिकांच्या सेवेसाठी',
          textAlign: narrow ? TextAlign.center : TextAlign.right,
          style: const TextStyle(fontSize: 12.5, color: AppColors.textSecondary, fontWeight: FontWeight.w600),
        ),
        Text(
          'आम्ही सदैव आपल्या सोबत!',
          textAlign: narrow ? TextAlign.center : TextAlign.right,
          style: const TextStyle(fontSize: 17, color: AppColors.navyText, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(width: 40, height: 3, color: AppColors.saffron),
            const SizedBox(width: 6),
            const CongressHand(size: 26, showLabel: false),
            const SizedBox(width: 6),
            Container(width: 40, height: 3, color: AppColors.green),
          ],
        ),
      ],
    );

    return Column(
      children: [
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(colors: [Color(0xFFFFF4EC), Colors.white, Color(0xFFEDF7F0)]),
            border: Border(top: BorderSide(color: AppColors.border)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1100),
              child: narrow
                  ? Column(children: [leader, const SizedBox(height: 14), slogan])
                  : Row(children: [Flexible(child: leader), const SizedBox(width: 16), Flexible(child: slogan)]),
            ),
          ),
        ),
        Container(
          color: AppColors.navy,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1100),
              child: Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                runSpacing: 6,
                children: [
                  const Text.rich(
                    TextSpan(
                      children: [
                        WidgetSpan(alignment: PlaceholderAlignment.middle, child: Icon(Icons.shield_rounded, size: 14, color: Colors.white70)),
                        TextSpan(text: '  आपली माहिती सुरक्षित आहे. कोणतीही वैयक्तिक माहिती संग्रहित केली जात नाही.'),
                      ],
                    ),
                    style: TextStyle(fontSize: 10.5, color: Colors.white70),
                  ),
                  Text('© ${DateTime.now().year} Electoral Roll Search  |  सर्व हक्क राखीव', style: const TextStyle(fontSize: 10.5, color: Colors.white70)),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
