import 'dart:math';

import 'package:flutter/material.dart';

import '../models/box.dart';
import '../services/audio_service.dart';
import '../services/isar_service.dart';
import '../widgets/lucky_wheel_painter.dart';

class LuckyWheelScreen extends StatefulWidget {
  const LuckyWheelScreen({super.key, required this.box});

  final BoxModel box;

  @override
  State<LuckyWheelScreen> createState() => _LuckyWheelScreenState();
}

class _LuckyWheelScreenState extends State<LuckyWheelScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  List<String> _items = [];
  String? _selected;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    );
    _load();
  }

  Future<void> _load() async {
    final isar = IsarService.instance.isar;
    final tasks = await isar.taskModels
        .filter()
        .boxIdEqualTo(widget.box.id)
        .and()
        .isCompletedEqualTo(false)
        .findAll();
    setState(() => _items = tasks.map((e) => e.content).toList());
  }

  @override
  Widget build(BuildContext context) {
    final color = Color(int.parse('FF${widget.box.color.replaceAll('#', '')}', radix: 16));

    return SizedBox(
      height: MediaQuery.of(context).size.height * 0.8,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: _items.isEmpty
            ? const Center(child: Text('盒子是空的，先去添加任务吧'))
            : Column(
                children: [
                  Expanded(
                    child: RotationTransition(
                      turns: CurvedAnimation(parent: _controller, curve: Curves.easeInOutCubic),
                      child: CustomPaint(
                        painter: LuckyWheelPainter(items: _items, baseColor: color),
                        child: const SizedBox.expand(),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: _spin,
                    child: const Text('开始'),
                  ),
                  if (_selected != null) Text('抽中了：$_selected'),
                ],
              ),
      ),
    );
  }

  Future<void> _spin() async {
    await AudioService.instance.playTick();
    await _controller.forward(from: 0);
    final item = _items[Random().nextInt(_items.length)];
    setState(() => _selected = item);
    await AudioService.instance.playStop();

    if (!mounted) return;
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        content: Text('抽中了：$item'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('好的')),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}
