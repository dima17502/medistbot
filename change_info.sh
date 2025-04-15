#!/bin/bash


i=1


for j in `ls infozero`;
do 


mv infozero/$j images/$i/info0.png


let "i = i + 1"
done

#ls images_backup1_oct/images/$i > images/$i/existing_images.txt


#ls images/extra_images > images/extra_images/existing_images.txt
