import 'dart:convert';

import 'package:dio/dio.dart';

class DeepSeekService {
  DeepSeekService(this._dio);

  final Dio _dio;

  Future<Map<String, dynamic>> extractTasks({
    required String apiKey,
    required List<String> boxNames,
    required String rawText,
  }) async {
    final systemPrompt = '''你是一个任务提取助手。用户会输入一段包含任务信息的文字，
请将其中的任务按盒子分类提取出来，返回严格的 JSON 格式：
{"boxes":[{"boxName":"重要事项","tasks":["任务1","任务2"]},{"boxName":"杂事","tasks":["任务3"]}]}
只返回 JSON，不要有其他文字。可用盒子名称：${boxNames.join('、')}''';

    final response = await _dio.post(
      'https://api.deepseek.com/chat/completions',
      options: Options(headers: {'Authorization': 'Bearer $apiKey'}),
      data: {
        'model': 'deepseek-chat',
        'messages': [
          {'role': 'system', 'content': systemPrompt},
          {'role': 'user', 'content': rawText},
        ],
      },
    );

    final content =
        response.data['choices'][0]['message']['content']?.toString() ?? '{}';
    return jsonDecode(content) as Map<String, dynamic>;
  }
}
