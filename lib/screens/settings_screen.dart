import 'package:flutter/material.dart';

import '../services/isar_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _apiController = TextEditingController();
  String _theme = 'system';
  bool _show = false;
  bool _soundEnabled = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final isar = IsarService.instance.isar;
    final settings = await isar.settingsModels.where().findFirst();
    if (settings == null) return;
    setState(() {
      _apiController.text = settings.deepseekApiKey;
      _theme = settings.themeMode;
      _soundEnabled = settings.completionSoundEnabled;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _apiController,
            obscureText: !_show,
            decoration: InputDecoration(
              labelText: 'DeepSeek API Key',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
              suffixIcon: IconButton(
                icon: Icon(_show ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _show = !_show),
              ),
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _theme,
            decoration: InputDecoration(
              labelText: '主题模式',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
            ),
            items: const [
              DropdownMenuItem(value: 'system', child: Text('跟随系统')),
              DropdownMenuItem(value: 'light', child: Text('浅色')),
              DropdownMenuItem(value: 'dark', child: Text('深色')),
            ],
            onChanged: (v) => setState(() => _theme = v ?? 'system'),
          ),
          SwitchListTile(
            value: _soundEnabled,
            onChanged: (v) => setState(() => _soundEnabled = v),
            title: const Text('完成音效开关'),
          ),
          ListTile(
            title: const Text('关于 TaskBox'),
            subtitle: const Text('轻量、游戏化任务管理工具。'),
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: _save, child: const Text('保存设置')),
        ],
      ),
    );
  }

  Future<void> _save() async {
    final isar = IsarService.instance.isar;
    final settings = await isar.settingsModels.where().findFirst();
    if (settings == null) return;

    settings.deepseekApiKey = _apiController.text.trim();
    settings.themeMode = _theme;
    settings.completionSoundEnabled = _soundEnabled;

    await isar.writeTxn(() async {
      await isar.settingsModels.put(settings);
    });

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已保存')));
  }
}
