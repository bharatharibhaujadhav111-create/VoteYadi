import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Rounded white card used throughout both dashboards.
class AppCard extends StatelessWidget {
  const AppCard({super.key, required this.child, this.padding = const EdgeInsets.all(18), this.color});

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: color ?? Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
        boxShadow: const [BoxShadow(color: Color(0x0F000000), blurRadius: 14, offset: Offset(0, 4))],
      ),
      padding: padding,
      child: child,
    );
  }
}

/// Section heading with an icon, e.g. "🔍 नाव शोधा".
class SectionTitle extends StatelessWidget {
  const SectionTitle({super.key, required this.icon, required this.title, this.iconColor, this.trailing, this.center = false});

  final IconData icon;
  final String title;
  final Color? iconColor;
  final Widget? trailing;
  final bool center;

  @override
  Widget build(BuildContext context) {
    final text = Text(
      title,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      textAlign: center ? TextAlign.center : TextAlign.start,
      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AppColors.navyText),
    );
    if (center && trailing == null) {
      // Centered variant: let the text shrink instead of overflowing the row.
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 20, color: iconColor ?? AppColors.saffron),
          const SizedBox(width: 8),
          Flexible(child: text),
        ],
      );
    }
    return Row(
      children: [
        Icon(icon, size: 20, color: iconColor ?? AppColors.saffron),
        const SizedBox(width: 8),
        Expanded(child: text),
        if (trailing != null) ...[const SizedBox(width: 8), trailing!],
      ],
    );
  }
}

class Pill extends StatelessWidget {
  const Pill({super.key, required this.label, this.color = AppColors.surface, this.textColor = AppColors.textSecondary, this.icon, this.maxWidth = 260});

  final String label;
  final Color color;
  final Color textColor;
  final IconData? icon;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: label,
      waitDuration: const Duration(milliseconds: 500),
      child: Container(
        constraints: BoxConstraints(maxWidth: maxWidth),
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[Icon(icon, size: 13, color: textColor), const SizedBox(width: 4)],
            Flexible(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                maxLines: 1,
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: textColor),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class LoadingIndicator extends StatelessWidget {
  const LoadingIndicator({super.key, this.message});
  final String? message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(width: 36, height: 36, child: CircularProgressIndicator(strokeWidth: 3, color: AppColors.saffron)),
          if (message != null) ...[
            const SizedBox(height: 14),
            Text(message!, style: const TextStyle(color: AppColors.textSecondary)),
          ],
        ],
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.subtitle, this.action});

  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(color: AppColors.saffronLight, borderRadius: BorderRadius.circular(36)),
            child: Icon(icon, size: 34, color: AppColors.saffron),
          ),
          const SizedBox(height: 16),
          Text(title, textAlign: TextAlign.center, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AppColors.navyText)),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(subtitle!, textAlign: TextAlign.center, style: const TextStyle(color: AppColors.textSecondary, height: 1.4)),
          ],
          if (action != null) ...[const SizedBox(height: 16), action!],
        ],
      ),
    );
  }
}

class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.message, this.onRetry});
  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return EmptyState(
      icon: Icons.error_outline_rounded,
      title: 'काहीतरी चूक झाली',
      subtitle: message,
      action: onRetry == null
          ? null
          : OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh_rounded), label: const Text('पुन्हा प्रयत्न करा')),
    );
  }
}

/// Simple numbered pagination bar.
class PaginationBar extends StatelessWidget {
  const PaginationBar({super.key, required this.page, required this.totalPages, required this.onChanged});

  final int page;
  final int totalPages;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    if (totalPages <= 1) return const SizedBox.shrink();
    final pages = <int>{1, totalPages, page, page - 1, page + 1, page - 2, page + 2}.where((p) => p >= 1 && p <= totalPages).toList()..sort();
    final children = <Widget>[];
    children.add(_navBtn(Icons.chevron_left_rounded, page > 1 ? () => onChanged(page - 1) : null));
    int? last;
    for (final p in pages) {
      if (last != null && p - last > 1) {
        children.add(const Padding(padding: EdgeInsets.symmetric(horizontal: 4), child: Text('…', style: TextStyle(color: AppColors.textMuted))));
      }
      children.add(_pageBtn(p));
      last = p;
    }
    children.add(_navBtn(Icons.chevron_right_rounded, page < totalPages ? () => onChanged(page + 1) : null));
    return Wrap(alignment: WrapAlignment.center, crossAxisAlignment: WrapCrossAlignment.center, spacing: 4, runSpacing: 4, children: children);
  }

  Widget _navBtn(IconData icon, VoidCallback? onTap) => IconButton(onPressed: onTap, icon: Icon(icon), color: AppColors.navyText);

  Widget _pageBtn(int p) {
    final active = p == page;
    return InkWell(
      onTap: active ? null : () => onChanged(p),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        width: 36,
        height: 36,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: active ? AppColors.saffron : Colors.white,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: active ? AppColors.saffron : AppColors.border),
        ),
        child: Text('$p', style: TextStyle(fontWeight: FontWeight.w700, color: active ? Colors.white : AppColors.navyText)),
      ),
    );
  }
}

/// Max-width centered column used for page content.
class PageContainer extends StatelessWidget {
  const PageContainer({super.key, required this.child, this.maxWidth = 1100, this.padding = const EdgeInsets.symmetric(horizontal: 16, vertical: 16)});
  final Widget child;
  final double maxWidth;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

void showSnack(BuildContext context, String message, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(message),
      backgroundColor: error ? AppColors.danger : AppColors.navy,
    ));
}
