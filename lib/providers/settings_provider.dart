import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/settings.dart';
import '../services/isar_service.dart';

final settingsProvider = FutureProvider<SettingsModel>((ref) async {
  final isar = IsarService.instance.isar;
  return await isar.settingsModels.where().findFirst() ?? SettingsModel();
});

final themeModeProvider = Provider<ThemeMode>((ref) {
  final settings = ref.watch(settingsProvider).value;
  switch (settings?.themeMode) {
    case 'light':
      return ThemeMode.light;
    case 'dark':
      return ThemeMode.dark;
    default:
      return ThemeMode.system;
  }
});
