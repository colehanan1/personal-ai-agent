from integrations.weather import WeatherAPI

if __name__ == "__main__":
    w = WeatherAPI()
    print(w.current_weather())

