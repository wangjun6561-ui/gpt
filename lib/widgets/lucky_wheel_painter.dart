import 'dart:math';

import 'package:flutter/material.dart';

class LuckyWheelPainter extends CustomPainter {
  LuckyWheelPainter({required this.items, required this.baseColor});

  final List<String> items;
  final Color baseColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (items.isEmpty) return;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;
    final sweep = 2 * pi / items.length;

    for (int i = 0; i < items.length; i++) {
      final paint = Paint()
        ..color = Color.lerp(baseColor, Colors.black, (i % 5) * 0.08) ?? baseColor;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        i * sweep,
        sweep,
        true,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
