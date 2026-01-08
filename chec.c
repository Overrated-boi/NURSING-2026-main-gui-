#include <stdio.h>

int main() {
    int num, temp, sum = 0, digit;

    printf("Enter a number: ");
    scanf("%d", &num);

    temp = num;

    while (temp != 0) {
        digit = temp % 10; //3
        sum += digit * digit * digit;  // cube of each digit
        temp /= 10;
    }

    if (sum == num)
        printf("Armstrong Number");
    else
        printf("Not Armstrong");

    return 0;
}
