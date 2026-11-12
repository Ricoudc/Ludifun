import 'package:flutter/material.dart';

import '../models/level.dart';
import 'theme.dart';

Color levelColor(int level) => switch (Levels.color(level)) {
  'green' => LudiColors.mastered,
  'orange' => LudiColors.toReview,
  'red' => LudiColors.notMastered,
  _ => Colors.black26,
};

/// Niveau de 0 à 5 en étoiles, lu par les lecteurs d'écran avec son libellé.
class LevelStars extends StatelessWidget {
  const LevelStars(this.level, {this.size = 18, super.key});

  final int level;
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = levelColor(level);
    return Semantics(
      label: 'Niveau $level sur ${Levels.max} : ${Levels.label(level)}',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 1; i <= Levels.max; i++)
            Icon(
              i <= level ? Icons.star_rounded : Icons.star_outline_rounded,
              size: size,
              color: i <= level ? color : Colors.black26,
            ),
        ],
      ),
    );
  }
}
