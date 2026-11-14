import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/theme.dart';
import 'package:ludifun/core/display.dart';

void main() {
  test('§5.94 : l\'affichage se garde et se relit, un contenu illisible vaut « normal »', () {
    const chosen = DisplaySettings(
      textSize: TextSize.larger,
      easyReading: true,
      highContrast: true,
    );
    final back = DisplaySettings.fromJson(chosen.toJson());
    expect(back.textSize, TextSize.larger);
    expect(back.easyReading && back.highContrast, isTrue);
    final unknown = DisplaySettings.fromJson({'text_size': 'énorme'});
    expect(unknown.textSize, TextSize.normal);
    expect(unknown.easyReading || unknown.highContrast, isFalse);
  });

  test('§5.94 : lecture facile espace lettres et lignes ; contraste renforcé : noir sur blanc', () {
    final base = buildTheme();
    expect(applyDisplay(base, const DisplaySettings()), same(base));
    final easy = applyDisplay(base, const DisplaySettings(easyReading: true));
    expect(easy.textTheme.bodyLarge?.letterSpacing, 0.8);
    expect(easy.textTheme.bodyLarge?.height, 1.5);
    expect(easy.textTheme.bodyLarge?.fontSize, base.textTheme.bodyLarge?.fontSize);
    final strong = applyDisplay(base, const DisplaySettings(highContrast: true));
    expect(strong.scaffoldBackgroundColor, Colors.white);
    expect(strong.textTheme.bodyMedium?.color, Colors.black);
  });

  testWidgets('§5.94 : la taille choisie s\'ajoute à celle du système', (tester) async {
    late double scale;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(1.1)),
        child: Builder(
          builder: (context) => withTextSize(
            context,
            const DisplaySettings(textSize: TextSize.larger),
            Builder(
              builder: (context) {
                scale = MediaQuery.textScalerOf(context).scale(10);
                return const SizedBox();
              },
            ),
          ),
        ),
      ),
    );
    expect(scale, closeTo(10 * 1.1 * 1.4, 0.001));
  });
}
