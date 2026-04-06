import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../services/deepseek_service.dart';
import '../services/isar_service.dart';

class AIExtractSheet extends StatefulWidget {
  const AIExtractSheet({super.key});

  @override
  State<AIExtractSheet> createState() => _AIExtractSheetState();
}

class _AIExtractSheetState extends State<AIExtractSheet> {
  final _controller = TextEditingController();
  bool _loading = false;
  Map<String, List<String>> _preview = {};

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: MediaQuery.of(context).size.height * 0.7,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('AI 智能提取', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            TextField(
              controller: _controller,
              minLines: 5,
              maxLines: 7,
              decoration: InputDecoration(
                hintText: '输入你的任务文本，例如：重要事项有开会、写报告，杂事有买菜、回消息…',
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('使用 DeepSeek AI · 点击配置 API Key')),
            const SizedBox(height: 8),
            if (_preview.isNotEmpty)
              Expanded(
                child: ListView(
                  children: _preview.entries
                      .map((e) => ListTile(title: Text(e.key), subtitle: Text(e.value.join('、'))))
                      .toList(),
                ),
              ),
            const Spacer(),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _loading ? null : _extract,
                child: _loading ? const CircularProgressIndicator() : const Text('✦ 开始提取'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _extract() async {
    final setting = await IsarService.instance.getSettings();
    if (setting.deepseekApiKey.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请先配置 API Key')));
      return;
    }

    setState(() => _loading = true);
    try {
      final boxes = await IsarService.instance.getBoxes();
      final service = DeepSeekService(Dio());
      final result = await service.extractTasks(
        apiKey: setting.deepseekApiKey,
        boxNames: boxes.map((e) => e.name).toList(),
        rawText: _controller.text,
      );
      final parsed = <String, List<String>>{};
      for (final box in (result['boxes'] as List<dynamic>)) {
        parsed[box['boxName'] as String] = (box['tasks'] as List<dynamic>).map((e) => e.toString()).toList();
      }
      if (mounted) setState(() => _preview = parsed);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
}
