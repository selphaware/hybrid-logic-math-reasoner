@echo off
echo.
echo === Const^(^) usages outside numeric/Fraction patterns ===
echo === String literals will appear here too - visually scan past them ===
echo === Anything that is NOT a string literal is potentially out of scope ===
echo.

git grep -n "Const(" src/ tests/ | findstr /V /R /C:"Const([0-9]" /C:"Const(-[0-9]" /C:"Const(Fraction"

echo.
echo === Done ===
