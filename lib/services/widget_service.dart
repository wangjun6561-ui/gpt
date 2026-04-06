import 'package:home_widget/home_widget.dart';

class WidgetService {
  static const _androidName = 'TaskBoxWidgetProvider';

  Future<void> updateImportantWidget({
    required List<String> topFiveTasks,
    required int pending,
    required double progress,
  }) async {
    await HomeWidget.saveWidgetData<String>('box_name', '重要事项');
    await HomeWidget.saveWidgetData<int>('pending_count', pending);
    await HomeWidget.saveWidgetData<String>('tasks', topFiveTasks.join('\n'));
    await HomeWidget.saveWidgetData<double>('progress', progress);

    await HomeWidget.updateWidget(
      androidName: _androidName,
      iOSName: _androidName,
    );
  }
}
