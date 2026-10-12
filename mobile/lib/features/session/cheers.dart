import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../app/theme.dart';

/// Ce qui rend la correction vivante (point 4) : étoiles gagnées, série de bonnes réponses,
/// confettis quand c'est juste, petite secousse quand ce ne l'est pas. Rien de tout cela ne
/// compte dans la note : c'est seulement pour le plaisir de l'enfant.

/// Étoiles d'un jeu : 3 tout juste, 2 presque (60 % ou plus), 1 pour un début, 0 sinon.
int starsFor(double score) => switch (score) {
  >= 1 => 3,
  >= 0.6 => 2,
  > 0 => 1,
  _ => 0,
};

bool _calm(BuildContext context) => MediaQuery.maybeDisableAnimationsOf(context) ?? false;

/// Trois étoiles qui apparaissent l'une après l'autre ; celles non gagnées restent grises.
class StarsRow extends StatefulWidget {
  const StarsRow(this.stars, {this.onStar, super.key});

  final int stars;

  /// Appelé à chaque étoile qui apparaît (petit son).
  final VoidCallback? onStar;

  @override
  State<StarsRow> createState() => _StarsRowState();
}

class _StarsRowState extends State<StarsRow> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );
  int _announced = 0;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      final shown = (_controller.value * 3).floor().clamp(0, widget.stars);
      while (_announced < shown) {
        _announced++;
        widget.onStar?.call();
      }
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_calm(context)) {
      _controller.value = 1;
    } else if (!_controller.isAnimating && _controller.value == 0) {
      _controller.forward();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Semantics(
    label: '${widget.stars} étoile${widget.stars > 1 ? 's' : ''} sur 3',
    child: ExcludeSemantics(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (var i = 0; i < 3; i++)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Transform.scale(
                  scale: i < widget.stars ? _pop(_controller.value * 3 - i) : 1,
                  child: Icon(
                    i < widget.stars ? Icons.star_rounded : Icons.star_outline_rounded,
                    key: Key(i < widget.stars ? 'star-earned' : 'star-empty'),
                    size: 48,
                    color: i < widget.stars ? const Color(0xFFFFC107) : Colors.black26,
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );

  /// 0 avant son tour, puis grossit un peu plus que nature et revient à 1.
  static double _pop(double t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return Curves.elasticOut.transform(t);
  }
}

/// « 🔥 3 bonnes réponses d'affilée ! » à partir de 3.
class StreakChip extends StatelessWidget {
  const StreakChip(this.streak, {super.key});

  final int streak;

  @override
  Widget build(BuildContext context) {
    if (streak < 3) return const SizedBox.shrink();
    return Center(
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: _calm(context) ? 1 : 0.6, end: 1),
        duration: const Duration(milliseconds: 500),
        curve: Curves.elasticOut,
        builder: (context, scale, child) => Transform.scale(scale: scale, child: child),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: LudiColors.accent.withValues(alpha: 0.18),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Text(
            '🔥 $streak bonnes réponses d\'affilée !',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
          ),
        ),
      ),
    );
  }
}

/// Confettis par-dessus [child] quand c'est juste, petite secousse quand ce ne l'est pas.
class Cheer extends StatefulWidget {
  const Cheer({required this.child, required this.happy, super.key});

  final Widget child;

  /// true : confettis ; false : secousse.
  final bool happy;

  @override
  State<Cheer> createState() => _CheerState();
}

class _CheerState extends State<Cheer> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: Duration(milliseconds: widget.happy ? 1200 : 450),
  );
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (!_calm(context)) _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: _controller,
    child: widget.child,
    builder: (context, child) {
      final t = _controller.value;
      if (!widget.happy) {
        // Trois petits allers-retours qui s'amortissent.
        final dx = math.sin(t * math.pi * 6) * 10 * (1 - t);
        return Transform.translate(offset: Offset(dx, 0), child: child);
      }
      return Stack(
        clipBehavior: Clip.none,
        fit: StackFit.passthrough, // la carte garde toute la largeur
        children: [
          child!,
          if (_controller.isAnimating)
            Positioned.fill(
              child: IgnorePointer(child: CustomPaint(painter: _Confetti(t))),
            ),
        ],
      );
    },
  );
}

class _Confetti extends CustomPainter {
  _Confetti(this.t);

  final double t;

  static const _colors = [
    Color(0xFFFFC107),
    Color(0xFF4CAF50),
    Color(0xFF2196F3),
    Color(0xFFE91E63),
    Color(0xFFFF9800),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final random = math.Random(7); // mêmes confettis à chaque fois : dessin stable
    final origin = Offset(size.width / 2, size.height * 0.4);
    for (var i = 0; i < 28; i++) {
      final angle = random.nextDouble() * math.pi * 2;
      final speed = 80 + random.nextDouble() * 140;
      final position =
          origin +
          Offset(math.cos(angle), math.sin(angle)) * speed * t +
          Offset(0, 160 * t * t); // ils retombent
      final paint = Paint()
        ..color = _colors[i % _colors.length].withValues(alpha: (1 - t).clamp(0, 1));
      canvas.save();
      canvas.translate(position.dx, position.dy);
      canvas.rotate(angle + t * 6);
      canvas.drawRect(const Rect.fromLTWH(-4, -2, 8, 4), paint);
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(_Confetti old) => old.t != t;
}

/// « 🎲 Jeu du jour » au-dessus du jeu choisi pour aujourd'hui (§5.54).
class DailyGameBanner extends StatelessWidget {
  const DailyGameBanner(this.name, {super.key});

  final String name;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
    decoration: BoxDecoration(
      gradient: const LinearGradient(colors: [Color(0xFFFFE082), Color(0xFFFFCC80)]),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Text(
      '🎲 Jeu du jour : $name · étoiles ×2',
      textAlign: TextAlign.center,
      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
    ),
  );
}
