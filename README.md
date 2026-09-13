Casual Projects build!

### AI + Scraping
I had AI scrape clothing from 12 niche clothing brands and use CLIP to create a vectors with 512 dimensions for each piece of clothing.



### Hinge Style feedback
A single piece of clothing appears on the screen, you can swipe left or right. Each piece of clothing is a vector indicating style.
The taste vector associated with the reccomendation is adjusted with weights -1, 1, and 2 (super like) based on the response.


### Reccomendations
I've been learning the process of how to do basic reccomendations. So far the first step is always normalizing, then subtracting the corpus average. We normalize so that the we don't have to use the distance formula for the cosine similarity and we subtract the corpus average to exaggerate the difference in products-- in this case clothing (the average in this dataset was a black t-shirt)


- cosine similarity. This is just a dot product thanks to step 1, it's returning how similar their angles are. 


#### What gets shown to me?
The design is a queue of 12 pieces of clothing. It includes the top 10 matches, but also the most uncertain and one random to continue training and give variance. 




### One taste vector?
It's flawed to use one taste vector because if you liked two very dissimilar things it would average them to create a mediocre vector that splits the two. In this case I used 4 taste vectors that were initially randomly placed.



### Hosting
Hosted with cloudflare + linux pc.
