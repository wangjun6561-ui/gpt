import 'package:flutter/material.dart';

import '../models/task.dart';

class TaskItem extends StatelessWidget {
  const TaskItem({
    super.key,
    required this.task,
    required this.accent,
    required this.onToggle,
    required this.onEdit,
  });

  final TaskModel task;
  final Color accent;
  final VoidCallback onToggle;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final overdue = task.dueDate != null && task.dueDate!.isBefore(DateTime.now());
    return ListTile(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      leading: InkWell(
        onTap: onToggle,
        child: Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            color: task.isCompleted ? accent : Colors.transparent,
            shape: BoxShape.circle,
            border: Border.all(color: accent, width: 2),
          ),
          child: task.isCompleted
              ? const Icon(Icons.check, color: Colors.white, size: 16)
              : null,
        ),
      ),
      title: InkWell(
        onTap: onEdit,
        child: Text(
          task.content,
          style: TextStyle(
            fontSize: 14,
            decoration: task.isCompleted ? TextDecoration.lineThrough : null,
            color: task.isCompleted ? Colors.grey : null,
          ),
        ),
      ),
      subtitle: task.dueDate == null
          ? null
          : Text(
              '截止 ${task.dueDate!.year}-${task.dueDate!.month}-${task.dueDate!.day}',
              style: TextStyle(fontSize: 12, color: overdue ? Colors.red : Colors.grey),
            ),
      trailing: const Icon(Icons.drag_indicator),
    );
  }
}
