import 'package:flutter/material.dart';

import '../../../core/models/models.dart';
import '../../../core/theme/app_theme.dart';

/// Replica of the original electoral-roll voter slip printed in the PDF:
///
///  ┌───┐                         ZCG7133341
///  │ 2 │
///  └───┘   Name : Bhagyashri Sharad Aaglave   ┌──────────┐
///          Husband's Name: sharad aaglave     │          │
///          House Number :                     │  Photo   │
///          Age : 31  Gender : Female           │Available │
///                                              └──────────┘
///
/// Shown inside each search result so the searcher sees exactly the same
/// fields / layout that appear on the printed voter list (booth) page.
class VoterSlipCard extends StatelessWidget {
  const VoterSlipCard({required this.result, super.key});
  final VoterResult result;

  @override
  Widget build(BuildContext context) {
    final r = result;
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.textPrimary, width: 1),
        borderRadius: BorderRadius.circular(2),
        color: Colors.white,
      ),
      padding: const EdgeInsets.all(10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left: serial box + name/relation/house/age-gender lines.
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (r.serial.isNotEmpty)
                  Container(
                    constraints: const BoxConstraints(minWidth: 40),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                    decoration: BoxDecoration(
                      border: Border.all(color: AppColors.textPrimary, width: 1),
                    ),
                    child: Text(
                      r.serial,
                      textAlign: TextAlign.right,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                    ),
                  ),
                const SizedBox(height: 8),
                _SlipLine(label: 'Name', value: r.name),
                _SlipLine(label: r.relationLabelEn, value: r.relationName),
                _SlipLine(label: 'House Number', value: r.house),
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Wrap(
                    spacing: 4,
                    children: [
                      Text.rich(
                        TextSpan(
                          children: [
                            const TextSpan(text: 'Age : ', style: TextStyle(fontSize: 12.5, color: AppColors.textPrimary)),
                            TextSpan(
                              text: r.age.isEmpty ? '—' : r.age,
                              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                            ),
                            const TextSpan(text: '  Gender : ', style: TextStyle(fontSize: 12.5, color: AppColors.textPrimary)),
                            TextSpan(
                              text: r.gender.isEmpty ? '—' : r.gender,
                              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          // Right: EPIC number + photo placeholder box.
          SizedBox(
            width: 96,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  r.epic.isEmpty ? '—' : r.epic,
                  textAlign: TextAlign.right,
                  style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
                ),
                const SizedBox(height: 6),
                Container(
                  width: 90,
                  height: 78,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    border: Border.all(color: AppColors.textPrimary, width: 1),
                  ),
                  child: const Text(
                    'Photo\nAvailable',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 11.5, color: AppColors.textMuted, height: 1.4),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SlipLine extends StatelessWidget {
  const _SlipLine({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(text: '$label : ', style: const TextStyle(fontSize: 12.5, color: AppColors.textPrimary)),
            TextSpan(
              text: value.isEmpty ? ' ' : value,
              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
            ),
          ],
        ),
      ),
    );
  }
}
