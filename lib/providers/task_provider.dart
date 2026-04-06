import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/task.dart';
import '../services/audio_service.dart';
import '../services/isar_service.dart';
import '../services/widget_service.dart';

final tasksByBoxProvider = FutureProvider.family<List<TaskModel>, int>((ref, boxId) async {
  final isar = IsarService.instance.isar;
  return isar.taskModels.filter().boxIdEqualTo(boxId).sortBySortOrder().findAll();
});

final taskActionsProvider = Provider<TaskActions>((ref) {
  return TaskActions();
});

class TaskActions {
  final _widgetService = WidgetService();

  Future<void> toggleTask(TaskModel task) async {
    final isar = IsarService.instance.isar;

    task.isCompleted = !task.isCompleted;
    task.completedAt = task.isCompleted ? DateTime.now() : null;

    await isar.writeTxn(() async => isar.taskModels.put(task));

    if (task.isCompleted) {
      await AudioService.instance.playComplete();
    }

    await _refreshImportantWidget();
  }

  Future<void> _refreshImportantWidget() async {
    final isar = IsarService.instance.isar;
    final important =
        await isar.boxModels.filter().nameEqualTo('重要事项').findFirst();
    if (important == null) return;

    final tasks = await isar.taskModels
        .filter()
        .boxIdEqualTo(important.id)
        .sortBySortOrder()
        .findAll();

    final pendingList = tasks.where((e) => !e.isCompleted).toList();
    final pending = pendingList.length;
    final total = tasks.length;
    final progress = total == 0 ? 0.0 : (total - pending) / total;

    await _widgetService.updateImportantWidget(
      topFiveTasks: pendingList.take(5).map((e) => e.content).toList(),
      pending: pending,
      progress: progress,
    );
  }
}
