import 'package:flutter/material.dart';

/// Calm, trustworthy palette used across the public and admin interfaces.
class AppColors {
  AppColors._();

  // Legacy token names are retained to keep existing widgets stable while
  // replacing the visually dominant orange palette with emerald.
  static const saffron = Color(0xFF15803D);
  static const saffronDark = Color(0xFF166534);
  static const saffronLight = Color(0xFFF0FDF4);
  static const green = Color(0xFF15803D);
  static const greenDark = Color(0xFF166534);
  static const greenLight = Color(0xFFF0FDF4);
  static const whatsapp = Color(0xFF25D366);
  static const navy = Color(0xFF05244C);
  static const navyText = Color(0xFF0D2B5B);
  static const blue = Color(0xFF1E63C8);
  static const purple = Color(0xFF6D3FC4);
  static const surface = Color(0xFFF7F8FA);
  static const card = Colors.white;
  static const border = Color(0xFFE6E9EE);
  static const textPrimary = Color(0xFF1B1F27);
  static const textSecondary = Color(0xFF636B7A);
  static const textMuted = Color(0xFF9AA3B2);
  static const danger = Color(0xFFD64545);
}

class AppTheme {
  AppTheme._();

  static ThemeData light() {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.green,
        primary: AppColors.green,
        secondary: AppColors.green,
        surface: AppColors.surface,
      ),
      scaffoldBackgroundColor: AppColors.surface,
    );
    return base.copyWith(
      textTheme: base.textTheme.apply(
        bodyColor: AppColors.textPrimary,
        displayColor: AppColors.textPrimary,
        fontFamily: 'Roboto',
      ),
      cardTheme: CardThemeData(
        color: AppColors.card,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: AppColors.border),
        ),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.saffron, width: 1.6),
        ),
        hintStyle: const TextStyle(color: AppColors.textMuted),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.saffron,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.navyText,
          side: const BorderSide(color: AppColors.border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: AppColors.green),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: Colors.white,
        side: const BorderSide(color: AppColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        labelStyle: const TextStyle(color: AppColors.textPrimary, fontSize: 13),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.border,
        thickness: 1,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
      dialogTheme: DialogThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      tabBarTheme: const TabBarThemeData(
        labelColor: AppColors.saffron,
        indicatorColor: AppColors.saffron,
        unselectedLabelColor: AppColors.textSecondary,
      ),
    );
  }
}
