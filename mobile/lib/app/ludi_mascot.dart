import 'package:flutter/material.dart';

/// Petite mascotte vectorielle intégrée à l'application : aucune image distante.
class LudiMascot extends StatelessWidget {
  const LudiMascot({this.size = 88, super.key});

  final double size;

  @override
  Widget build(BuildContext context) => Semantics(
    image: true,
    label: 'Ludi, le renard qui accompagne tes apprentissages',
    child: ExcludeSemantics(
      child: SizedBox.square(
        dimension: size,
        child: CustomPaint(painter: _LudiMascotPainter()),
      ),
    ),
  );
}

class _LudiMascotPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final fill = Paint()..style = PaintingStyle.fill;
    final stroke = Paint()
      ..color = const Color(0xFF7C3E25)
      ..strokeWidth = w * 0.025
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    canvas.drawCircle(
      Offset(w * 0.5, h * 0.52),
      w * 0.48,
      fill..color = const Color(0xFFBDEBE2),
    );

    final ears = Path()
      ..moveTo(w * 0.16, h * 0.39)
      ..lineTo(w * 0.19, h * 0.04)
      ..quadraticBezierTo(w * 0.21, h * 0.0, w * 0.25, h * 0.05)
      ..lineTo(w * 0.42, h * 0.29)
      ..close()
      ..moveTo(w * 0.58, h * 0.29)
      ..lineTo(w * 0.75, h * 0.05)
      ..quadraticBezierTo(w * 0.79, h * 0.0, w * 0.81, h * 0.04)
      ..lineTo(w * 0.84, h * 0.39)
      ..close();
    canvas.drawPath(ears, fill..color = const Color(0xFFE9854F));

    final innerEars = Path()
      ..moveTo(w * 0.22, h * 0.27)
      ..lineTo(w * 0.23, h * 0.11)
      ..lineTo(w * 0.34, h * 0.29)
      ..close()
      ..moveTo(w * 0.66, h * 0.29)
      ..lineTo(w * 0.77, h * 0.11)
      ..lineTo(w * 0.78, h * 0.27)
      ..close();
    canvas.drawPath(innerEars, fill..color = const Color(0xFFFFC4A4));

    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(w * 0.5, h * 0.55),
        width: w * 0.72,
        height: h * 0.67,
      ),
      fill..color = const Color(0xFFF39A5B),
    );

    canvas.drawCircle(
      Offset(w * 0.37, h * 0.59),
      w * 0.085,
      fill..color = const Color(0xFFF7B7A8),
    );
    canvas.drawCircle(
      Offset(w * 0.63, h * 0.59),
      w * 0.085,
      fill..color = const Color(0xFFF7B7A8),
    );

    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(w * 0.5, h * 0.68),
        width: w * 0.43,
        height: h * 0.25,
      ),
      fill..color = const Color(0xFFFFF7E9),
    );

    fill.color = const Color(0xFF392B2A);
    canvas.drawCircle(Offset(w * 0.39, h * 0.47), w * 0.035, fill);
    canvas.drawCircle(Offset(w * 0.61, h * 0.47), w * 0.035, fill);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(w * 0.5, h * 0.64),
        width: w * 0.105,
        height: h * 0.07,
      ),
      fill,
    );

    final smile = Path()
      ..moveTo(w * 0.5, h * 0.675)
      ..quadraticBezierTo(w * 0.46, h * 0.73, w * 0.43, h * 0.70)
      ..moveTo(w * 0.5, h * 0.675)
      ..quadraticBezierTo(w * 0.54, h * 0.73, w * 0.57, h * 0.70);
    canvas.drawPath(smile, stroke);
  }

  @override
  bool shouldRepaint(covariant _LudiMascotPainter oldDelegate) => false;
}
