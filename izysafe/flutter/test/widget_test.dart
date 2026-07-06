import 'package:flutter_test/flutter_test.dart';

import 'package:izysafe_parent/features/children/child.dart';

void main() {
  test('Child.fromJson parses the /children envelope shape', () {
    final c = Child.fromJson({
      'id': 'abc',
      'name': 'Aanya Kapoor',
      'nickname': null,
      'photo_url': null,
      'school_name': 'Sunrise Public School',
      'class_grade': '3B',
      'device_count': 1,
      'permissions': {'role': 'parent'},
    });
    expect(c.name, 'Aanya Kapoor');
    expect(c.schoolName, 'Sunrise Public School');
    expect(c.deviceCount, 1);
    expect(c.role, 'parent');
    expect(c.initials, 'AK');
  });

  test('Child.initials handles a single name', () {
    final c = Child.fromJson({'id': 'x', 'name': 'Vivaan', 'device_count': 0});
    expect(c.initials, 'V');
  });
}
