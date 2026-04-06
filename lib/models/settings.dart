import 'package:isar/isar.dart';

part 'settings.g.dart';

@collection
class SettingsModel {
  Id id = Isar.autoIncrement;

  String deepseekApiKey = '';
  String themeMode = 'system';
  bool completionSoundEnabled = true;

  SettingsModel();
}
