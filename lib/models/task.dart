class TaskModel {
  int? id;

  late int boxId;
  late String content;
  late bool isCompleted;
  late int sortOrder;
  int priority = 1;
  DateTime? dueDate;
  DateTime? completedAt;
  late DateTime createdAt;

  TaskModel();

  Map<String, Object?> toMap() {
    return {
      'id': id,
      'box_id': boxId,
      'content': content,
      'is_completed': isCompleted ? 1 : 0,
      'sort_order': sortOrder,
      'priority': priority,
      'due_date': dueDate?.toIso8601String(),
      'completed_at': completedAt?.toIso8601String(),
      'created_at': createdAt.toIso8601String(),
    };
  }

  static TaskModel fromMap(Map<String, Object?> map) {
    final model = TaskModel()
      ..id = map['id'] as int
      ..boxId = map['box_id'] as int
      ..content = map['content'] as String
      ..isCompleted = (map['is_completed'] as int) == 1
      ..sortOrder = map['sort_order'] as int
      ..priority = map['priority'] as int
      ..dueDate = map['due_date'] == null ? null : DateTime.parse(map['due_date'] as String)
      ..completedAt =
          map['completed_at'] == null ? null : DateTime.parse(map['completed_at'] as String)
      ..createdAt = DateTime.parse(map['created_at'] as String);
    return model;
  }
}
