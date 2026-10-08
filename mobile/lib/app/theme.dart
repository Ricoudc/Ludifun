import 'package:flutter/material.dart';

/// Couleurs de Ludifun, et les trois couleurs de maîtrise communes au bilan de
/// l'enfant et au tableau de bord du parent (§9.3).
abstract final class LudiColors {
  static const primary = Color(0xFF5B4FE0); // violet
  static const accent = Color(0xFFFF9F1C); // orange
  static const background = Color(0xFFF7F5FF);
  static const mastered = Color(0xFF2EB872);
  static const toReview = Color(0xFFFF9F1C);
  static const notMastered = Color(0xFFE5484D);
}

/// Thème unique : gros textes et grosses cibles tactiles pour les enfants dès le CP.
ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: LudiColors.primary,
    primary: LudiColors.primary,
    secondary: LudiColors.accent,
    surface: Colors.white,
  );
  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(18));
  return base.copyWith(
    scaffoldBackgroundColor: LudiColors.background,
    textTheme: base.textTheme.copyWith(
      headlineMedium: base.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
      titleLarge: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
      bodyLarge: base.textTheme.bodyLarge?.copyWith(fontSize: 18),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: LudiColors.background,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        shape: shape,
        textStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
      ),
    ),
    // Boutons secondaires (« Encore de l'aide », « Faire une pause »…) : aussi lisibles que les
    // principaux pour un enfant de CP.
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        shape: shape,
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(48, 48),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: Colors.white,
      shape: shape,
      margin: EdgeInsets.zero,
    ),
    inputDecorationTheme: InputDecorationTheme(
      helperMaxLines: 4,
      errorMaxLines: 4,
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
    ),
  );
}
