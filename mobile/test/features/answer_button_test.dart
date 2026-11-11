import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/session/activities/common.dart';

void main() {
  testWidgets('une réponse jaune sélectionnée reste lisible sans dépendre de la couleur', (
    tester,
  ) async {
    var selected = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: StatefulBuilder(
              builder: (context, setState) => AnswerButton(
                label: 'Option jaune',
                leading: 'B',
                color: LudiColors.accent,
                selected: selected,
                onPressed: () => setState(() => selected = true),
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.byIcon(Icons.check_circle), findsNothing);
    await tester.tap(find.text('Option jaune'));
    await tester.pump();

    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    final label = tester.widget<Text>(find.text('Option jaune'));
    expect(label.style?.color, Colors.black87);

    final marker = tester.widget<CircleAvatar>(find.byType(CircleAvatar));
    expect(marker.backgroundColor, Colors.black87);
    expect(marker.foregroundColor, LudiColors.accent);
  });
}
