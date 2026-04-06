class SettingsModel {
  int? id;

  String deepseekApiKey = '';
  String themeMode = 'system';

  SettingsModel();

  Map<String, Object?> toMap() {
    return {
      'id': id,
      'deepseek_api_key': deepseekApiKey,
      'theme_mode': themeMode,
    };
  }

  static SettingsModel fromMap(Map<String, Object?> map) {
    final model = SettingsModel()
      ..id = map['id'] as int
      ..deepseekApiKey = map['deepseek_api_key'] as String
      ..themeMode = map['theme_mode'] as String;
    return model;
  }
}
