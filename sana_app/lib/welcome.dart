import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'signup.dart';

class WelcomePage extends StatefulWidget {
  const WelcomePage({super.key});

  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage> {
  final FlutterTts _flutterTts = FlutterTts();

  @override
  void initState() {
    super.initState();

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Future.delayed(const Duration(milliseconds: 700));
      if (!mounted) return;
      await _speak('مرحبًا بكِ في تطبيقِ سَنَا');
    });
  }

  Future<void> _speak(String text) async {
    await _flutterTts.setLanguage('ar-SA');
    await _flutterTts.setSpeechRate(0.45);
    await _flutterTts.setPitch(1.0);
    await _flutterTts.speak(text);
  }

  @override
  void dispose() {
    _flutterTts.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const burgundy = Color(0xFF640000);

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        body: Container(
          width: double.infinity,
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: [0.0, 0.5, 1.0],
              colors: [
                Color(0xFFFFFFFF),
                Color(0xFFFFF3F3),
                Color(0xFFE3A9A9),
              ],
            ),
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
              child: Column(
                children: [
                  const SizedBox(height: 25),
                  const Text(
                    'مرحبا بك',
                    style: TextStyle(
                      fontSize: 80,
                      fontWeight: FontWeight.bold,
                      color: burgundy,
                    ),
                  ),
                  const SizedBox(height: 40),
                  Center(
                    child: SizedBox(
                      width: 400,
                      height: 300,
                      child: Image.asset(
                        'assets/images/sana-logo.png',
                        fit: BoxFit.contain,
                      ),
                    ),
                  ),
                  const Spacer(),
                  Center(
                    child: SizedBox(
                      width: 344,
                      height: 70,
                      child: ElevatedButton(
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => const SignupPage(),
                            ),
                          );
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: burgundy,
                          foregroundColor: Colors.white,
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                        ),
                        child: const Text(
                          'إنشاء حساب جديد',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 45,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}