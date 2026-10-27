def is_palindrome(text):
    clean_text = str(text).lower()
    return clean_text == clean_text[::-1]
    
print(is_palindrome("Radar"))
print(is_palindrome("racecar"))
print(is_palindrome("airbus"))
print(is_palindrome("boeing"))

def palindrome(code):
    low = 0
    high = len(code) -1
    while low<high:
        if code[low].lower() != code[high].lower():
            return False
        low +=1
        high -=1
    return True
    
print(palindrome("Racecar"))

first_array = (1,2,3,4,5,6,7,8)

def contain_duplicate():
    new_array = set(first_array)
    if len(new_array) != len(first_array):
        return True
    return False
print(contain_duplicate())



array = [1,4,6,8,2,3,9,7]

def largest_second_lar():
    highest = 0
    second_highest = 0
    for num in array:
        if num > highest:
            second_highest = highest
            highest = num
        elif num > second_highest and num != highest:
            second_highest = num
    return highest, second_highest
print(largest_second_lar())


def count_frequency(text):
    tally = {}
    for char in text:
        if char not in tally:
            tally[char] = 1
        else:
            tally[char] += 1
    return tally

print(count_frequency("hello"))


def reverse_array(arr):
    low = 0
    high = len(arr) -1
    while low < high:
        arr[low],arr[high] = arr[high], arr[low]
        low +=1
        high -=1
    return arr
    
print(reverse_array([1, 2, 3, 4, 5]))



def stock(prices):
    if not prices:
        return 0
    min_price = prices[0]
    max_profit = 0
    for price in prices:
        if min_price > price:
            min_price = price
        elif price - min_price > max_profit:
            max_profit = price - min_price
    return max_profit
    
print(stock([7, 1, 5, 3, 6, 4]))