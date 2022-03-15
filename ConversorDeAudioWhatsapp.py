from pydub import AudioSegment


#procurar como baixar o audio do whatsapp automaticamente
AudioSegment.from_ogg("teste.ogg").export("teste.mp3", format="mp3")