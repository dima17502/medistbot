#!/bin/bash


i=1

while [ $i -lt 148 ]
do
ls images/$i > images/$i/existing_images.txt
let "i = i + 1"
done

ls images/extra_images > images/extra_images/existing_images.txt

