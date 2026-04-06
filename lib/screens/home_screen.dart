import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/box_provider.dart';
import '../services/isar_service.dart';
import '../utils/transitions.dart';
import '../widgets/box_card.dart';
import '../widgets/today_overview_card.dart';
import 'ai_extract_sheet.dart';
import 'box_detail_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final boxesAsync = ref.watch(boxesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('TaskBox', style: TextStyle(fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            icon: const Icon(Icons.auto_awesome),
            onPressed: () => showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              builder: (_) => const AIExtractSheet(),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.push(
              context,
              SlidePageRoute(page: const SettingsScreen()),
            ),
          ),
        ],
      ),
      floatingActionButton: PopupMenuButton<String>(
        icon: const CircleAvatar(child: Icon(Icons.add)),
        onSelected: (value) {
          if (value == 'ai') {
            showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              builder: (_) => const AIExtractSheet(),
            );
          }
        },
        itemBuilder: (_) => const [
          PopupMenuItem(value: 'manual', child: Text('＋ 手动添加任务')),
          PopupMenuItem(value: 'ai', child: Text('✦ AI 智能提取')),
        ],
      ),
      body: boxesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, s) => Center(child: Text('加载失败: $e')),
        data: (boxes) {
          return FutureBuilder<Map<int, List<dynamic>>>(
            future: _loadTaskMap(boxes.map((e) => e.id).toList()),
            builder: (context, snapshot) {
              final taskMap = snapshot.data ?? {};
              final total = taskMap.values.fold<int>(0, (p, e) => p + e.length);
              final done = taskMap.values.fold<int>(
                0,
                (p, e) => p + e.where((t) => t.isCompleted == true).length,
              );

              return ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  TodayOverviewCard(total: total, done: done),
                  const SizedBox(height: 16),
                  ...boxes.map((box) {
                    final tasks = taskMap[box.id] ?? [];
                    final pending = tasks.where((e) => !e.isCompleted).length;
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: BoxCard(
                        box: box,
                        pending: pending,
                        total: tasks.length,
                        height: box.sortOrder == 0
                            ? 140
                            : box.sortOrder <= 2
                                ? 120
                                : 100,
                        onTap: () => Navigator.push(
                          context,
                          SlidePageRoute(page: BoxDetailScreen(box: box)),
                        ),
                      ),
                    );
                  }),
                ],
              );
            },
          );
        },
      ),
    );
  }

  Future<Map<int, List<dynamic>>> _loadTaskMap(List<int> boxIds) async {
    final map = <int, List<dynamic>>{};
    for (final id in boxIds) {
      map[id] = await IsarService.instance.getTasksByBoxId(id);
    }
    return map;
  }
}
