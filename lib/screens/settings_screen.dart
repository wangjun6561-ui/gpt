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

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final settings = await IsarService.instance.getSettings();
    setState(() {
      _apiController.text = settings.deepseekApiKey;
      _theme = settings.themeMode;
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
    final settings = await IsarService.instance.getSettings();
    settings.deepseekApiKey = _apiController.text.trim();
    settings.themeMode = _theme;

    await IsarService.instance.updateSettings(settings);

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已保存')));
  }
}
