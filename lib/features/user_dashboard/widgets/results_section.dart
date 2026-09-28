import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/common_widgets.dart';
import '../../pdf_viewer/pdf_viewer.dart';
import '../search_controller.dart';
import 'voter_slip_card.dart';

/// Search results: loading / error / empty / list + pagination.
class ResultsSection extends StatelessWidget {
  const ResultsSection({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.watch<VoterSearchController>();
    if (c.loading && c.response == null) {
      return const AppCard(
        child: LoadingIndicator(message: 'मतदार यादीत शोधत आहे...'),
      );
    }
    if (c.error != null) {
      return AppCard(
        child: ErrorState(message: c.error!, onRetry: () => c.search(c.query)),
      );
    }
    final r = c.response;
    if (r == null) return const SizedBox.shrink();
    if (r.total == 0) return _NoResults(response: r, controller: c);

    final parsed = r.query;
    final chips = <Widget>[];
    void chip(String label, String? v, IconData icon) {
      if (v != null && v.isNotEmpty) {
        chips.add(
          Pill(
            label: '$label: $v',
            icon: icon,
            color: AppColors.saffronLight,
            textColor: AppColors.saffronDark,
          ),
        );
      }
    }

    chip('नाव', parsed['name'] as String?, Icons.person_rounded);
    chip('वडील/पती', parsed['relation_name'] as String?, Icons.people_rounded);
    chip('EPIC', parsed['epic'] as String?, Icons.badge_rounded);
    chip('Booth', parsed['part'] as String?, Icons.tag_rounded);
    chip('लिंग', parsed['gender'] as String?, Icons.wc_rounded);
    if (parsed['age'] != null) {
      chip('वय', '${parsed['age']}', Icons.cake_rounded);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if ((parsed['transliterated'] as String? ?? '').isNotEmpty)
          Container(
            margin: const EdgeInsets.fromLTRB(4, 0, 4, 10),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.greenLight,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: AppColors.green.withValues(alpha: 0.25),
              ),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.translate_rounded,
                  size: 19,
                  color: AppColors.green,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      children: [
                        const TextSpan(
                          text: 'इंग्रजी नावाचा मराठी शोध: ',
                          style: TextStyle(color: AppColors.textSecondary),
                        ),
                        TextSpan(
                          text: parsed['transliterated'] as String,
                          style: const TextStyle(
                            fontWeight: FontWeight.w900,
                            color: AppColors.green,
                            fontSize: 15,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
          child: Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 8,
            runSpacing: 6,
            children: [
              Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: '${Formatters.count(r.total)} ',
                      style: const TextStyle(
                        fontWeight: FontWeight.w900,
                        color: AppColors.saffronDark,
                        fontSize: 16,
                      ),
                    ),
                    const TextSpan(
                      text: 'निकाल सापडले',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: AppColors.navyText,
                      ),
                    ),
                    if (c.selectedVillage.isNotEmpty)
                      TextSpan(
                        text: '  ·  ${c.selectedVillage}',
                        style: const TextStyle(
                          color: AppColors.green,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    TextSpan(
                      text: '  ·  ${r.tookMs.toStringAsFixed(0)} ms',
                      style: const TextStyle(
                        color: AppColors.textMuted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              ...chips,
              if (r.relaxed)
                const Pill(
                  label: 'जवळपास जुळणारे निकाल',
                  icon: Icons.auto_fix_high_rounded,
                  color: AppColors.greenLight,
                  textColor: AppColors.green,
                ),
            ],
          ),
        ),
        Stack(
          children: [
            Column(
              children: [
                for (var i = 0; i < r.results.length; i++) ...[
                  ResultCard(
                    result: r.results[i],
                    rank: (r.page - 1) * r.pageSize + i + 1,
                  ),
                  if (i < r.results.length - 1) const SizedBox(height: 8),
                ],
              ],
            ),
            if (c.loading)
              Positioned.fill(
                child: Container(
                  color: Colors.white.withValues(alpha: 0.55),
                  alignment: Alignment.center,
                  child: const CircularProgressIndicator(
                    color: AppColors.saffron,
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 12),
        PaginationBar(
          page: r.page,
          totalPages: r.totalPages,
          onChanged: c.goToPage,
        ),
      ],
    );
  }
}

class _NoResults extends StatelessWidget {
  const _NoResults({required this.response, required this.controller});
  final SearchResponse response;
  final VoterSearchController controller;

  static final _eciSearch = Uri.parse('https://electoralsearch.eci.gov.in/');
  static final _form6 = Uri.parse('https://voters.eci.gov.in/');
  static final _blo = Uri.parse('https://electoralsearch.eci.gov.in/');
  static final _helpline = Uri.parse('tel:1950');

  @override
  Widget build(BuildContext context) {
    final village = controller.selectedVillage;
    final narrow = MediaQuery.sizeOf(context).width < 640;
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: const Color(0xFFFDECEC),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.person_off_rounded,
                  color: AppColors.danger,
                  size: 24,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'या यादीमध्ये नाव सापडले नाही',
                      style: TextStyle(
                        fontSize: 16.5,
                        fontWeight: FontWeight.w800,
                        color: AppColors.navyText,
                      ),
                    ),
                    Text(
                      village.isEmpty
                          ? '"${controller.query}"  ·  सर्व गावे'
                          : '"${controller.query}"  ·  $village',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.greenLight,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFBFE3CC)),
            ),
            child: const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_rounded, size: 18, color: AppColors.green),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'काळजी करू नका. या PDF मध्ये नाव न सापडणे म्हणजे तुमचे नाव मतदार यादीतून निश्चितपणे वगळले आहे असे नाही.',
                    style: TextStyle(
                      fontSize: 12.5,
                      color: AppColors.green,
                      fontWeight: FontWeight.w600,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (response.suggestions.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Text(
              'तुम्हाला हे म्हणायचे होते का?',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: AppColors.textSecondary,
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final s in response.suggestions)
                  ActionChip(
                    avatar: const Icon(
                      Icons.person_search_rounded,
                      size: 16,
                      color: AppColors.saffronDark,
                    ),
                    label: Text(s),
                    backgroundColor: AppColors.saffronLight,
                    side: const BorderSide(color: Color(0xFFFFD3B8)),
                    labelStyle: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: AppColors.saffronDark,
                      fontSize: 13,
                    ),
                    onPressed: () => controller.search(s),
                  ),
              ],
            ),
          ],
          if (village.isNotEmpty) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                onPressed: () => controller.selectVillage(''),
                icon: const Icon(Icons.public_rounded, size: 18),
                label: const Text('सर्व गावांमध्ये शोधा'),
              ),
            ),
          ],
          const SizedBox(height: 16),
          const Divider(height: 1),
          const SizedBox(height: 14),
          const Text(
            'पुढील प्रक्रिया',
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w800,
              color: AppColors.navyText,
            ),
          ),
          const SizedBox(height: 10),
          const _Step(
            n: 1,
            icon: Icons.spellcheck_rounded,
            title: 'नावाच्या वेगवेगळ्या spelling ने पुन्हा शोधा',
            sub:
                'उदा. Vijay / Vijai, Jadhav / Jadav. फक्त पहिले नाव किंवा आडनाव टाकूनही पहा.',
          ),
          const _Step(
            n: 2,
            icon: Icons.verified_user_rounded,
            title: 'अधिकृत मतदार यादीमध्ये नाव तपासा',
            sub: 'ECI च्या अधिकृत शोध सेवेवर नाव / EPIC क्रमांकाने तपासा.',
          ),
          const _Step(
            n: 3,
            icon: Icons.note_add_rounded,
            title: 'नाव नसल्यास Form 6 द्वारे अर्ज करा',
            sub:
                'नवीन नाव समाविष्ट करण्यासाठी ऑनलाइन किंवा BLO कडे Form 6 भरा. माहिती चुकीची असल्यास Form 8.',
          ),
          const _Step(
            n: 4,
            icon: Icons.location_city_rounded,
            title: 'BLO / ERO कार्यालयाशी संपर्क साधा',
            sub: 'तुमच्या बूथचे BLO पडताळणीसाठी मदत करतील.',
          ),
          const _Step(
            n: 5,
            icon: Icons.support_agent_rounded,
            title: 'SIR मदतीसाठी 1950 वर संपर्क साधा',
            sub: 'मतदार हेल्पलाइन (टोल-फ्री).',
            last: true,
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.green,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                ),
                onPressed: () => _open(context, _eciSearch),
                icon: const Icon(Icons.verified_user_rounded, size: 18),
                label: const Text('अधिकृत यादीत नाव तपासा'),
              ),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                ),
                onPressed: () => _open(context, _form6),
                icon: const Icon(Icons.note_add_rounded, size: 18),
                label: const Text('Form 6 भरा'),
              ),
              OutlinedButton.icon(
                onPressed: () => _open(context, _blo),
                icon: const Icon(Icons.person_pin_circle_rounded, size: 18),
                label: const Text('माझा BLO शोधा'),
              ),
              OutlinedButton.icon(
                onPressed: () => _open(context, _helpline),
                icon: const Icon(Icons.call_rounded, size: 18),
                label: Text(narrow ? '1950' : 'हेल्पलाइन 1950'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _open(BuildContext context, Uri uri) async {
    final ok = await launchUrl(
      uri,
      mode: LaunchMode.externalApplication,
      webOnlyWindowName: '_blank',
    );
    if (!ok && context.mounted) {
      showSnack(context, 'लिंक उघडता आली नाही', error: true);
    }
  }
}

class _Step extends StatelessWidget {
  const _Step({
    required this.n,
    required this.icon,
    required this.title,
    required this.sub,
    this.last = false,
  });
  final int n;
  final IconData icon;
  final String title;
  final String sub;
  final bool last;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            Container(
              width: 28,
              height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: n.isOdd ? AppColors.saffron : AppColors.green,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Text(
                '$n',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  fontSize: 13,
                ),
              ),
            ),
            if (!last) Container(width: 2, height: 22, color: AppColors.border),
          ],
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: last ? 0 : 8, top: 2),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(icon, size: 15, color: AppColors.textSecondary),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        title,
                        style: const TextStyle(
                          fontSize: 13.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.navyText,
                        ),
                      ),
                    ),
                  ],
                ),
                Text(
                  sub,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textMuted,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// One voter result card with Open / Open at page / Download buttons.
class ResultCard extends StatelessWidget {
  const ResultCard({required this.result, required this.rank, super.key});
  final VoterResult result;
  final int rank;

  @override
  Widget build(BuildContext context) {
    final viewer = context.read<PdfViewer>();
    final narrow = MediaQuery.sizeOf(context).width < 640;
    final r = result;
    return AppCard(
      padding: EdgeInsets.zero,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                width: 5,
                color: rank.isOdd ? AppColors.saffron : AppColors.green,
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 34,
                            height: 34,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: AppColors.saffronLight,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              r.name.isNotEmpty ? r.name[0].toUpperCase() : '?',
                              style: const TextStyle(
                                fontWeight: FontWeight.w900,
                                color: AppColors.saffronDark,
                                fontSize: 16,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  r.name,
                                  style: const TextStyle(
                                    fontSize: 16.5,
                                    fontWeight: FontWeight.w800,
                                    color: AppColors.navyText,
                                  ),
                                ),
                                if (r.relationName.isNotEmpty)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 2),
                                    child: Text.rich(
                                      TextSpan(
                                        children: [
                                          TextSpan(
                                            text: '${r.relationLabel}: ',
                                            style: const TextStyle(
                                              color: AppColors.textMuted,
                                              fontSize: 12.5,
                                            ),
                                          ),
                                          TextSpan(
                                            text: r.relationName,
                                            style: const TextStyle(
                                              color: AppColors.textPrimary,
                                              fontWeight: FontWeight.w600,
                                              fontSize: 13.5,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          if (!narrow) _Meta(r: r),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          if (r.village.isNotEmpty)
                            Pill(
                              label: r.village,
                              icon: Icons.location_on_rounded,
                              color: AppColors.greenLight,
                              textColor: AppColors.green,
                            ),
                          if (r.part.isNotEmpty)
                            Pill(
                              label: 'Booth ${r.part}',
                              icon: Icons.tag_rounded,
                            ),
                          Pill(
                            label: 'पान ${r.page}',
                            icon: Icons.menu_book_rounded,
                            color: const Color(0xFFE8F0FC),
                            textColor: AppColors.blue,
                          ),
                          Pill(
                            label: r.pdfName,
                            icon: Icons.picture_as_pdf_rounded,
                            color: AppColors.saffronLight,
                            textColor: AppColors.saffronDark,
                          ),
                          if (r.serial.isNotEmpty)
                            Pill(label: 'क्र. ${r.serial}'),
                          if (r.epic.isNotEmpty)
                            Pill(label: r.epic, icon: Icons.badge_outlined),
                          if (narrow &&
                              (r.age.isNotEmpty || r.gender.isNotEmpty))
                            Pill(
                              label: [
                                if (r.gender.isNotEmpty) _genderMr(r.gender),
                                if (r.age.isNotEmpty) 'वय ${r.age}',
                              ].join(' · '),
                            ),
                          if (r.house.isNotEmpty)
                            Pill(
                              label: 'घर ${r.house}',
                              icon: Icons.home_outlined,
                            ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      VoterSlipCard(result: r),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          ElevatedButton.icon(
                            style: ElevatedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 11,
                              ),
                              backgroundColor: AppColors.green,
                            ),
                            onPressed: () => viewer.preview(
                              context,
                              r.pdf,
                              page: r.page,
                              voterId: r.id,
                              title: r.pdfName,
                            ),
                            icon: const Icon(
                              Icons.find_in_page_rounded,
                              size: 18,
                            ),
                            label: Text('पान ${r.page} वर उघडा'),
                          ),
                          OutlinedButton.icon(
                            onPressed: () => viewer.printSlip(context, r.id),
                            icon: const Icon(Icons.print_rounded, size: 17),
                            label: const Text('मतदार स्लिप प्रिंट करा'),
                          ),
                          OutlinedButton.icon(
                            onPressed: () => viewer.download(context, r.pdf),
                            icon: const Icon(Icons.download_rounded, size: 17),
                            label: const Text('डाउनलोड'),
                          ),
                          OutlinedButton(
                            style: OutlinedButton.styleFrom(
                              foregroundColor: AppColors.greenDark,
                              side: const BorderSide(color: AppColors.whatsapp),
                            ),
                            onPressed: () => _shareOnWhatsApp(context, r),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                _WhatsAppMark(),
                                SizedBox(width: 8),
                                Text('WhatsApp शेअर'),
                                SizedBox(width: 6),
                                Icon(Icons.arrow_forward_rounded, size: 18),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _genderMr(String g) {
    switch (g.toLowerCase()) {
      case 'male':
        return 'पुरुष';
      case 'female':
        return 'स्त्री';
      default:
        return g;
    }
  }

  static Future<void> _shareOnWhatsApp(
    BuildContext context,
    VoterResult voter,
  ) async {
    final details = <String>[
      'मतदार माहिती',
      '',
      'नाव: ${voter.name}',
      if (voter.relationName.isNotEmpty)
        '${voter.relationLabel}: ${voter.relationName}',
      if (voter.village.isNotEmpty) 'गाव: ${voter.village}',
      if (voter.serial.isNotEmpty) 'अनुक्रमांक: ${voter.serial}',
      if (voter.part.isNotEmpty) 'भाग / बूथ क्रमांक: ${voter.part}',
      if (voter.epic.isNotEmpty) 'मतदार ओळखपत्र: ${voter.epic}',
      if (voter.age.isNotEmpty) 'वय: ${voter.age}',
      if (voter.gender.isNotEmpty) 'लिंग: ${_genderMr(voter.gender)}',
      'PDF पान: ${voter.page}',
    ].join('\n');
    final uri = Uri.https('wa.me', '/', {'text': details});
    final opened = await launchUrl(
      uri,
      mode: LaunchMode.externalApplication,
      webOnlyWindowName: '_blank',
    );
    if (!opened && context.mounted) {
      showSnack(context, 'WhatsApp उघडता आले नाही', error: true);
    }
  }
}

class _WhatsAppMark extends StatelessWidget {
  const _WhatsAppMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 22,
      height: 22,
      decoration: const BoxDecoration(
        color: AppColors.whatsapp,
        shape: BoxShape.circle,
      ),
      child: const Icon(Icons.phone_rounded, color: Colors.white, size: 14),
    );
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.r});
  final VoterResult r;

  @override
  Widget build(BuildContext context) {
    final parts = <String>[];
    if (r.gender.isNotEmpty) parts.add(ResultCard._genderMr(r.gender));
    if (r.age.isNotEmpty) parts.add('वय ${r.age}');
    if (parts.isEmpty) return const SizedBox.shrink();
    return Text(
      parts.join(' · '),
      style: const TextStyle(
        fontSize: 12.5,
        color: AppColors.textSecondary,
        fontWeight: FontWeight.w600,
      ),
    );
  }
}
