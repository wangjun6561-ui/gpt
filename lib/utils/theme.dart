import 'package:flutter/material.dart';

class AppTheme {
  static const lightBg = Color(0xFFF8F9FA);
  static const darkBg = Color(0xFF1A1A2E);

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        brightness: Brightness.light,
        scaffoldBackgroundColor: lightBg,
        cardTheme: const CardTheme(
          elevation: 2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(24)),
          ),
        ),
      );

  static ThemeData get dark => ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: darkBg,
      );
}
