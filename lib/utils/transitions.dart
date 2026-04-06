import 'package:flutter/material.dart';

class SlidePageRoute<T> extends PageRouteBuilder<T> {
  SlidePageRoute({required Widget page})
      : super(
          pageBuilder: (_, __, ___) => page,
          transitionDuration: const Duration(milliseconds: 200),
          reverseTransitionDuration: const Duration(milliseconds: 200),
          transitionsBuilder: (_, animation, __, child) {
            return SlideTransition(
              position: Tween(begin: const Offset(1, 0), end: Offset.zero).animate(
                CurvedAnimation(parent: animation, curve: Curves.easeInOut),
              ),
              child: child,
            );
          },
        );
}
