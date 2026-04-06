import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/box.dart';
import '../models/task.dart';
import '../providers/task_provider.dart';
import '../services/isar_service.dart';
import '../widgets/progress_bar.dart';
import '../widgets/task_item.dart';
import 'lucky_wheel_screen.dart';

class BoxDetailScreen extends ConsumerStatefulWidget {
  const BoxDetailScreen({super.key, required this.box});

  final BoxModel box;

  @override
  ConsumerState<BoxDetailScreen> createState() => _BoxDetailScreenState();
}

class _BoxDetailScreenState extends ConsumerState<BoxDetailScreen> {
  bool _showCompleted = false;

  @override
  Widget build(BuildContext context) {
    final boxId = widget.box.id!;
    final tasksAsync = ref.watch(tasksByBoxProvider(boxId));

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.box.name),
        actions: [
          IconButton(
            icon: const Icon(Icons.casino_outlined),
            onPressed: () => showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              builder: (_) => LuckyWheelScreen(box: widget.box),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.info_outline),
            onPressed: () => _showDescription(context),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton(
            style: FilledButton.styleFrom(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
            onPressed: _addTask,
            child: const Text('＋ 添加任务'),
          ),
        ),
      ),
      body: tasksAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, s) => Center(child: Text('加载失败: $e')),
        data: (tasks) {
          final todo = tasks.where((e) => !e.isCompleted).toList();
          final done = tasks.where((e) => e.isCompleted).toList();
          final progress = tasks.isEmpty ? 0.0 : done.length / tasks.length;

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: ProgressBar(progress: progress, color: _hex(widget.box.color)),
              ),
              Expanded(
                child: ListView(
                  children: [
                    ...todo.map(
                      (task) => TaskItem(
                        task: task,
                        accent: _hex(widget.box.color),
                        onToggle: () async {
                          await ref.read(taskActionsProvider).toggleTask(task);
                          ref.invalidate(tasksByBoxProvider(boxId));
                        },
                        onEdit: () => _editTask(task),
                      ),
                    ),
                    ListTile(
                      title: Text('已完成 ${done.length} 项 ${_showCompleted ? '▴' : '▾'}'),
                      onTap: () => setState(() => _showCompleted = !_showCompleted),
                    ),
                    if (_showCompleted)
                      ...done.map(
                        (task) => TaskItem(
                          task: task,
                          accent: _hex(widget.box.color),
                          onToggle: () async {
                            await ref.read(taskActionsProvider).toggleTask(task);
                            ref.invalidate(tasksByBoxProvider(boxId));
                          },
                          onEdit: () => _editTask(task),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  void _showDescription(BuildContext context) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(20),
        child: Text(widget.box.description ?? '暂无介绍'),
      ),
    );
  }

  Future<void> _addTask() async {
    final boxId = widget.box.id!;
    final nextSort = await IsarService.instance.countTasksByBoxId(boxId);
    final task = TaskModel()
      ..boxId = boxId
      ..content = '新任务'
      ..isCompleted = false
      ..sortOrder = nextSort
      ..createdAt = DateTime.now();

    await IsarService.instance.insertTask(task);
    ref.invalidate(tasksByBoxProvider(boxId));
  }

  void _editTask(TaskModel task) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(16),
        child: Text('编辑功能预留：${task.content}'),
      ),
    );
  }

  Color _hex(String hex) => Color(int.parse('FF${hex.replaceAll('#', '')}', radix: 16));
}
