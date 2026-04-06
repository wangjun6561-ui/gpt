class BoxModel {
  int? id;

  late String name;
  late String color;
  late String icon;
  late int sortOrder;
  String? description;
  late bool isDefault;
  late DateTime createdAt;

  BoxModel();

  Map<String, Object?> toMap() {
    return {
      'id': id,
      'name': name,
      'color': color,
      'icon': icon,
      'sort_order': sortOrder,
      'description': description,
      'is_default': isDefault ? 1 : 0,
      'created_at': createdAt.toIso8601String(),
    };
  }

  static BoxModel fromMap(Map<String, Object?> map) {
    final model = BoxModel()
      ..id = map['id'] as int
      ..name = map['name'] as String
      ..color = map['color'] as String
      ..icon = map['icon'] as String
      ..sortOrder = map['sort_order'] as int
      ..description = map['description'] as String?
      ..isDefault = (map['is_default'] as int) == 1
      ..createdAt = DateTime.parse(map['created_at'] as String);
    return model;
  }
}
