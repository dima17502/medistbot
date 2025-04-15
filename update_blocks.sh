#!/bin/bash


i=1


for j in `ls blocks`;
do 
bj=($(ls blocks/$j/*.png))
ij=($(ls images/$i/[!i]*.png))
#echo "${#bj[@]} , ${#ij[@]}" 
if [[ ${#bj[@]} == ${#ij[@]} ]]; then
	ind=0
	for k in "${ij[@]}";
	do
		echo " $k -> ${bj[$ind]} "
		mv ${bj[$ind]} $k
		let "ind = ind + 1"
	done
fi
#    ${#distro[@]}
# for i in "${arrayName[@]}"
#for k in `ls images/$i/[!i]*.png`;

#mv infozero/$j images/$i/info0.png

let "i = i + 1"
done

#ls images_backup1_oct/images/$i > images/$i/existing_images.txt


#ls images/extra_images > images/extra_images/existing_images.txt
