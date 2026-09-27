import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Tricolor hero banner with the two leaders, title and Congress hand symbol.
class HeroHeader extends StatelessWidget {
  const HeroHeader({super.key});

  @override
  Widget build(BuildContext context) {
    final narrow = MediaQuery.sizeOf(context).width < 560;
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFFFFE9DA), Color(0xFFFFF8F3), Color(0xFFEAF6EE)],
        ),
      ),
      child: Stack(
        children: [
          // subtle tricolor top stripe
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Container(
              height: 5,
              decoration: const BoxDecoration(
                gradient: LinearGradient(colors: [AppColors.saffron, AppColors.saffron, Colors.white, AppColors.green, AppColors.green]),
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(12, 22, 12, narrow ? 14 : 18),
            child: Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _Leader(
                      asset: 'assets/images/praniti_shinde.jpg',
                      honorific: 'मा. खासदार',
                      name: 'प्रणितीताई शिंदे',
                      size: narrow ? 84 : 110,
                    ),
                    Expanded(child: _Title(narrow: narrow)),
                    _Leader(
                      asset: 'assets/images/sushilkumar_shinde.jpg',
                      honorific: 'मा. सुशीलकुमार शिंदे',
                      name: 'माजी केंद्रीय गृहमंत्री',
                      size: narrow ? 84 : 110,
                      nameFirst: true,
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: const [
                    Expanded(child: Divider(color: AppColors.saffron, thickness: 1)),
                    Padding(
                      padding: EdgeInsets.symmetric(horizontal: 10),
                      child: Text('यांच्या मार्गदर्शनाखाली', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: AppColors.navyText)),
                    ),
                    Expanded(child: Divider(color: AppColors.green, thickness: 1)),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Title extends StatelessWidget {
  const _Title({required this.narrow});
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
          decoration: BoxDecoration(color: AppColors.saffronLight, borderRadius: BorderRadius.circular(20), border: Border.all(color: const Color(0xFFFFD3B8))),
          child: const Text('ELECTORAL ROLL SEARCH', style: TextStyle(fontSize: 9.5, letterSpacing: 1.6, fontWeight: FontWeight.w800, color: AppColors.saffronDark)),
        ),
        const SizedBox(height: 6),
        Text(
          'मतदार यादी शोध केंद्र',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: narrow ? 21 : 30, fontWeight: FontWeight.w900, color: AppColors.navyText, height: 1.15),
        ),
        const SizedBox(height: 6),
        Text(
          'उत्तर सोलापूरतील नागरिकांना\nSIR नंतर मतदार यादीमध्ये नाव शोधण्यासाठी मदत',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: narrow ? 10.5 : 12.5, fontWeight: FontWeight.w600, color: AppColors.saffronDark, height: 1.35),
        ),
        const SizedBox(height: 8),
        const CongressHand(size: 52),
      ],
    );
  }
}

class _Leader extends StatelessWidget {
  const _Leader({required this.asset, required this.honorific, required this.name, required this.size, this.nameFirst = false});
  final String asset;
  final String honorific;
  final String name;
  final double size;
  final bool nameFirst;

  @override
  Widget build(BuildContext context) {
    final first = nameFirst ? name : honorific;
    final second = nameFirst ? honorific : name;
    return SizedBox(
      width: size + 24,
      child: Column(
        children: [
          Container(
            width: size,
            height: size,
            padding: const EdgeInsets.all(3),
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: [AppColors.saffron, Colors.white, AppColors.green], begin: Alignment.topLeft, end: Alignment.bottomRight),
              boxShadow: [BoxShadow(color: Color(0x22000000), blurRadius: 10, offset: Offset(0, 4))],
            ),
            child: ClipOval(child: Image.asset(asset, fit: BoxFit.cover, alignment: Alignment.topCenter)),
          ),
          const SizedBox(height: 6),
          Text(
            nameFirst ? second : first,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 10, color: AppColors.saffronDark, fontWeight: FontWeight.w700),
          ),
          Text(
            nameFirst ? first : second,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: nameFirst ? 11 : 12, color: AppColors.navyText, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

/// Official Indian National Congress emblem with the party name below.
class CongressHand extends StatelessWidget {
  const CongressHand({super.key, this.size = 44, this.showLabel = true, this.labelSize});
  final double size;
  final bool showLabel;
  final double? labelSize;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: Color(0x22000000), blurRadius: 6, offset: Offset(0, 2))],
          ),
          child: ClipOval(child: Image.asset('assets/images/congress_symbol.png', fit: BoxFit.cover)),
        ),
        if (showLabel) ...[
          SizedBox(height: size * 0.08),
          Text(
            'काँग्रेस',
            style: TextStyle(fontSize: labelSize ?? (size * 0.27).clamp(9.0, 14.0), fontWeight: FontWeight.w900, color: AppColors.navyText, letterSpacing: 0.2),
          ),
        ],
      ],
    );
  }
}
